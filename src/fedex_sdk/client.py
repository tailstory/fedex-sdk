"""Interacting with FedEx."""

from typing import Any
from xml.sax.saxutils import escape

import niquests
import xmltodict

PRODUCTION_URL = "https://ws.fedex.com/web-services"
#: FedEx's test environment.
TESTING_URL = "https://wsbeta.fedex.com/web-services"

TRACK_NAMESPACE = "http://fedex.com/ws/track/v19"


class FedExClient:
    """A class wrapping FedEx's Web Services, which take SOAP envelopes over HTTP."""

    def __init__(  # noqa: PLR0913 - each is a separate credential of the account or setting of the connection
        self,
        key: str,
        password: str,
        account_number: str,
        meter_number: str,
        *,
        base_url: str = PRODUCTION_URL,
        timeout: float = 60.0,
    ) -> None:
        """Initialize the FedExClient class.

        Parameters
        ----------
        key
            The Web Services key.
        password
            The Web Services password.
        account_number
            The FedEx account number.
        meter_number
            The meter number issued with the key.
        base_url
            The API endpoint: :data:`PRODUCTION_URL`, or :data:`TESTING_URL` for FedEx's test environment.
        timeout
            Seconds to wait for FedEx to answer.
        """
        self.base_url = base_url
        self.timeout = timeout
        self._key = key
        self._password = password
        self._account_number = account_number
        self._meter_number = meter_number
        self._session = niquests.Session()

    def _request(self, body: str) -> dict[str, Any]:
        """Send one SOAP body and parse the body of the answer.

        Parameters
        ----------
        body
            The request element, already serialized.
        """
        envelope = (
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            f"<soapenv:Header/><soapenv:Body>{body}</soapenv:Body></soapenv:Envelope>"
        )
        response = self._session.request(
            "POST",
            self.base_url,
            data=envelope.encode(),
            headers={"Content-Type": "text/xml;charset=utf-8"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        answer = xmltodict.parse(
            response.text or "",
            process_namespaces=True,
            namespaces={"http://schemas.xmlsoap.org/soap/envelope/": None, TRACK_NAMESPACE: None},
        )
        body_answer: dict[str, Any] = answer["Envelope"]["Body"]
        return body_answer

    def get_tracking(self, tracking_number: str) -> dict[str, Any]:
        """Read a package's tracking details.

        Parameters
        ----------
        tracking_number
            The package's tracking number.
        """
        credential = f"<v19:Key>{escape(self._key)}</v19:Key><v19:Password>{escape(self._password)}</v19:Password>"
        body = (
            f'<v19:TrackRequest xmlns:v19="{TRACK_NAMESPACE}">'
            "<v19:WebAuthenticationDetail>"
            f"<v19:UserCredential>{credential}</v19:UserCredential>"
            "</v19:WebAuthenticationDetail>"
            "<v19:ClientDetail>"
            f"<v19:AccountNumber>{escape(self._account_number)}</v19:AccountNumber>"
            f"<v19:MeterNumber>{escape(self._meter_number)}</v19:MeterNumber>"
            "</v19:ClientDetail>"
            "<v19:Version>"
            "<v19:ServiceId>trck</v19:ServiceId>"
            "<v19:Major>19</v19:Major><v19:Intermediate>0</v19:Intermediate><v19:Minor>0</v19:Minor>"
            "</v19:Version>"
            "<v19:SelectionDetails>"
            "<v19:PackageIdentifier>"
            "<v19:Type>TRACKING_NUMBER_OR_DOORTAG</v19:Type>"
            f"<v19:Value>{escape(tracking_number)}</v19:Value>"
            "</v19:PackageIdentifier>"
            "</v19:SelectionDetails>"
            "</v19:TrackRequest>"
        )
        reply: dict[str, Any] = self._request(body)["TrackReply"]
        return reply
