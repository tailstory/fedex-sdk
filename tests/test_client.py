"""Tests for the FedEx client. No call leaves the machine; numbers and names are invented."""

from http import HTTPStatus
from typing import Any

import pytest
import xmltodict
from niquests import HTTPError, Response

from fedex_sdk import FedExClient
from fedex_sdk.client import TRACK_NAMESPACE

TRACKING_NUMBER = "500000000000"

TRACKED = (
    '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">'
    "<SOAP-ENV:Header/><SOAP-ENV:Body>"
    f'<TrackReply xmlns="{TRACK_NAMESPACE}">'
    "<HighestSeverity>SUCCESS</HighestSeverity>"
    f"<CompletedTrackDetails><TrackDetails><TrackingNumber>{TRACKING_NUMBER}</TrackingNumber></TrackDetails>"
    "</CompletedTrackDetails>"
    "</TrackReply>"
    "</SOAP-ENV:Body></SOAP-ENV:Envelope>"
)

NAMESPACES = {"http://schemas.xmlsoap.org/soap/envelope/": None, TRACK_NAMESPACE: None}


def _response(status_code: int, body: str = "") -> Response:
    """Build a niquests Response without touching the network."""
    response = Response()
    response.status_code = status_code
    response._content = body.encode()  # noqa: SLF001 -- no public way to seed a canned body
    return response


class _SessionRecorder:
    """Stand-in for ``Session.request`` serving one canned response and recording calls."""

    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Response:  # noqa: ANN401 -- mirrors Session.request
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.response


def _client(response: Response) -> tuple[FedExClient, _SessionRecorder]:
    """Build a client whose session answers with ``response``."""
    client = FedExClient("key-one", "password-one", "account-one", "meter-one", base_url="https://fedex.invalid/ws")
    recorder = _SessionRecorder(response)
    vars(client)["_session"] = recorder
    return client, recorder


def _sent_request(recorder: _SessionRecorder) -> dict[str, Any]:
    """Parse the one track request the recorder saw."""
    (call,) = recorder.calls
    envelope = xmltodict.parse(call["data"], process_namespaces=True, namespaces=NAMESPACES)
    request: dict[str, Any] = envelope["Envelope"]["Body"]["TrackRequest"]
    return request


def test_tracking_answer_is_the_reply_inside_the_envelope() -> None:
    """The caller gets the track reply, without the SOAP wrapping or namespaces."""
    client, _ = _client(_response(HTTPStatus.OK, TRACKED))

    tracking = client.get_tracking(TRACKING_NUMBER)

    assert tracking["HighestSeverity"] == "SUCCESS"
    assert tracking["CompletedTrackDetails"]["TrackDetails"]["TrackingNumber"] == TRACKING_NUMBER


def test_tracking_request_carries_the_account_and_the_package() -> None:
    """The request signs in as this account and asks about this package."""
    client, recorder = _client(_response(HTTPStatus.OK, TRACKED))

    client.get_tracking(TRACKING_NUMBER)

    request = _sent_request(recorder)
    assert recorder.calls[0]["url"] == "https://fedex.invalid/ws"
    assert request["WebAuthenticationDetail"]["UserCredential"] == {"Key": "key-one", "Password": "password-one"}
    assert request["ClientDetail"] == {"AccountNumber": "account-one", "MeterNumber": "meter-one"}
    assert request["SelectionDetails"]["PackageIdentifier"]["Value"] == TRACKING_NUMBER


def test_tracking_number_cannot_break_out_of_the_request() -> None:
    """A tracking number with markup in it stays a value."""
    client, recorder = _client(_response(HTTPStatus.OK, TRACKED))
    hostile = "1</v19:Value><v19:Other>2"

    client.get_tracking(hostile)

    identifier = _sent_request(recorder)["SelectionDetails"]["PackageIdentifier"]
    assert identifier["Value"] == hostile
    assert "Other" not in identifier


def test_failed_request_raises() -> None:
    """An HTTP error from FedEx is raised, not parsed."""
    client, _ = _client(_response(HTTPStatus.INTERNAL_SERVER_ERROR))

    with pytest.raises(HTTPError):
        client.get_tracking(TRACKING_NUMBER)
