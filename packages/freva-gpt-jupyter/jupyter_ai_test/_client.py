from typing import Any, Mapping, Optional

import platform
import ipaddress
import httpx
import os
import urllib.request
from importlib import metadata

try:
  __version__ = metadata.version('freva-gpt')
except metadata.PackageNotFoundError:
  __version__ = '0.0.0'


class Client:
    def __init__(
        self,
        client: httpx.Client,
        host: Optional[str] = None,
        follow_redirects: bool = True,
        timeout: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        **kwargs,
    ) -> None:
        """
        Creates a httpx client. Default parameters are the same as those defined in httpx
        except for the following:
        - `follow_redirects`: True
        - `timeout`: None
        `kwargs` are passed to the httpx client.
        """

        self._client = client(
        base_url=self._parse_host(host or os.getenv('FREVAGPT_HOST')),
        follow_redirects=follow_redirects,
        timeout=timeout,
        # Lowercase all headers to ensure override
        headers={
            k.lower(): v
            for k, v in {
            **(headers or {}),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': f'frevagpt-python/{__version__} ({platform.machine()} {platform.system().lower()}) Python/{platform.python_version()}',
            }.items()
        },
        **kwargs,
        )

    def _request_raw(self, *args, **kwargs):
        r = self._client.request(*args, **kwargs)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise 
        return r
    
    def request(self, *args, stream:bool=False, **kwargs):
        # TODO: Implement streaming request
        return self._request_raw(*args, **kwargs).json()



    @classmethod
    def _parse_host(cls, host): 
        host, port = host or '', 11434
        scheme, _, hostport = host.partition('://')
        if not hostport:
            scheme, hostport = 'http', host
        elif scheme == 'http':
            port = 80
        elif scheme == 'https':
            port = 443

        split = urllib.parse.urlsplit('://'.join([scheme, hostport]))
        host = split.hostname or '127.0.0.1'
        port = split.port or port

        try:
            if isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address):
                # Fix missing square brackets for IPv6 from urlsplit
                host = f'[{host}]'
        except ValueError:
                raise

        if path := split.path.strip('/'):
            return f'{scheme}://{host}:{port}/{path}'

        return f'{scheme}://{host}:{port}'