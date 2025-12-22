import ipaddress
import json
import logging
import os
import platform
import socket
import urllib.parse
from importlib import metadata
from json.decoder import JSONDecodeError
from typing import Any, List, Mapping, Optional, Tuple, Union

import httpx

try:
  __version__ = metadata.version('jupyter_freva_gpt')
except metadata.PackageNotFoundError:
  __version__ = '0.0.0'

class Client:
    def __init__(
        self,
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

        self._client = httpx.Client(
            base_url=_parse_host(host or os.getenv('FREVAGPT_HOST')),
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
        self.logger = logging.getLogger(__name__)

    def _request_raw(self, *args, **kwargs):
        try:
            r = self._client.request(*args, **kwargs)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                e.response.read()
                raise ConnectionError(e.response.status_code, f"Error connecting to url {_parse_host(e.request.url)} with error: {e.response.text}") from None
        except httpx.ConnectError as e:
            raise ConnectionError(101, f"Failed to connect to {_parse_host(e.request.url)}. Please try again." ) from None
        return r
    
    def request(self, *args, stream=False, **kwargs):
        if stream:
            def inner():
                try:
                    with self._client.stream(*args, **kwargs) as r:
                        try:
                            r.raise_for_status()
                        except httpx.HTTPStatusError as e:
                            e.response.read()
                            raise ConnectionError(e.response.status_code, f"Error connecting to url {_parse_host(e.request.url)} with error: {e.response.text}") from None
                        complete_parts, partial_response = [], ""
                        for chunk in r.iter_bytes():
                            chunk_decoded = chunk.decode("utf-8")
                            complete_parts, partial_response = _process_chunks(chunk_decoded, partial_response)
                            if complete_parts:
                                for part in complete_parts:
                                    yield part
                except httpx.ConnectError as e:
                    raise ConnectionError(101, f"Failed to connect to url {_parse_host(e.request.url)}. Please try again." ) from None
            return inner()
        else:
            try:
                r=self._request_raw(*args, **kwargs)
                complete_parts, _ = _process_chunks(r.text)
                if complete_parts:
                    return complete_parts[0]
                else:
                    return r.json()
            except JSONDecodeError:
                self.logger.warning(
                    ("Encountered error when trying to decode the request from JSON.  Returning text instead.")
                )
                return r.text

class AsyncClient:
    def __init__(
        self,
        host: Optional[str] = None,
        follow_redirects: bool = True,
        timeout: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        **kwargs,
    ) -> None:
        """
        Creates an async httpx client. Default parameters are the same as those defined in httpx
        except for the following:
        - `follow_redirects`: True
        - `timeout`: None
        `kwargs` are passed to the httpx client.
        """

        self._client = httpx.AsyncClient(
            base_url=_parse_host(host or os.getenv('FREVAGPT_HOST')),
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
        self.logger = logging.getLogger(__name__)

    async def _request_raw(self, *args, **kwargs):
        try:
            r = await self._client.request(*args, **kwargs)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                e.response.aread()
                raise ConnectionError(e.response.status_code, f"Error connecting to url {_parse_host(e.request.url)} with error: {e.response.text}") from None
        except httpx.ConnectError as e:
            raise ConnectionError(101, f"Failed to connect to {_parse_host(e.request.url)}. Please try again." ) from None
        return r
    
    async def request(self, *args, stream=False, **kwargs):
        if stream:
            async def inner():
                try:
                    async with self._client.stream(*args, **kwargs) as r:
                        try:
                            r.raise_for_status()
                        except httpx.HTTPStatusError as e:
                            await e.response.aread()
                            raise ConnectionError(e.response.status_code, f"Error connecting to url {_parse_host(e.request.url)} with error: {e.response.text}") from None
                        complete_parts, partial_response = [], ""
                        async for chunk in r.aiter_bytes():
                            chunk_decoded = chunk.decode("utf-8")
                            complete_parts, partial_response = _process_chunks(chunk_decoded, partial_response)
                            if complete_parts:
                                for part in complete_parts:
                                    yield part
                except httpx.ConnectError as e:
                    raise ConnectionError(101, f"Failed to connect to url {e.request.url}. Please try again." ) from None
            return inner()
        else:
            try:
                r = await self._request_raw(*args, **kwargs)
                complete_parts, _ = _process_chunks(r.text)
                if complete_parts:
                    return complete_parts[0]
                else:
                    return r.json()
            except JSONDecodeError:
                self.logger.warning(
                    ("Encountered error when trying to decode the request from JSON.  Returning text instead.")
                )
                return r.text
    
def _process_chunks(chunk: str, partial_response: str = "") -> Tuple[List[dict], str]:
    """
    Processes a chunk of string data, which represent JSON-like objects split across chunks.

    Args:
    chunk (str): A string that may contain full or partial JSON-like objects.
    partial_response (str): A string that stores an incomplete JSON-like object from the previous chunk.

    Returns:
    Tuple[List[str], str]: A list of complete JSON-like objects and the partial string (if any).
    """
    

    def recurse_dict(d: dict[str, Any]) -> dict[str, Any]:
        """
        Make sure that all (possibly escaped) json-strings within a dictionary are parsed as dicts
        """
        for key, value in d.items():
            if isinstance(value, str):
                if value.startswith("{") and value.endswith("}"):
                    d[key]=recurse_dict(json.loads(value))
        return d
    # sanitize input string
    chunk = chunk.strip().strip('\n')
    # check that chunk is not empty
    if not chunk:
        return [], partial_response
    # Attempt to split the input chunk into potential JSON-like parts based on "}{"
    chunk_split = chunk.split("}{")
    # If there is no "}{", the chunk might represent a single or partial JSON-like object
    if len(chunk_split) == 1:
        # Case 1: The chunk starts with "{" and ends with "}" (a complete JSON object)
        if chunk[0] == "{" and chunk[-1] == "}":
            return [recurse_dict(json.loads(chunk))], ""
        
        # Case 2: The chunk starts with "{" but does not end with "}" (partial JSON object)
        elif chunk[0] == "{" and chunk[-1] != "}":
            partial_response = chunk  # Save the partial object for later
            return [], partial_response
        
        # Case 3: The chunk ends with "}" but does not start with "{" (completes a partial JSON object)
        elif chunk[-1] == "}":
            partial_response += chunk  # Append to the saved partial object
            return [recurse_dict(json.loads(partial_response))], ""  # Return the completed object
        
        # Case 4: Neither starts with "{" nor ends with "}" (still an incomplete JSON object)
        else:
            partial_response += chunk  # Append to the saved partial object
            return [], partial_response
    
    # If there are multiple parts after splitting, handle them as potential JSON objects
    else:
        complete_parts = [] 

        for i, part in enumerate(chunk_split):
            if i == 0:
                fixed_part = part + "}"  # Add closing brace to make it a complete object
                # Check if it is a continuation of a partial response
                if part[0] != "{":
                    partial_response += fixed_part  # Append to the saved partial object
                    complete_parts.append(recurse_dict(json.loads(partial_response)))  # Add the completed object to the list
                    continue
            
            elif i == len(chunk_split) - 1:
                fixed_part = "{" + part  # Add opening brace to make it a complete object
                # If it is still incomplete, save it as the new partial response
                if part[-1] != "}":
                    partial_response = fixed_part
                    return complete_parts, partial_response
                # If it is complete, add to the list and clear partial response
                complete_parts.append(recurse_dict(json.loads(fixed_part)))
                return complete_parts, ""
            
            else:
                fixed_part = "{" + part + "}" 
                
            complete_parts.append(recurse_dict(json.loads(fixed_part)))

def _parse_host(host: Union[str, httpx.URL]):
    host=str(host)
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
        try:
            socket.gethostbyname(host)    
        except socket.gaierror:
            raise ConnectionError(
                (f"Temporary failure in name resolution of host {host}. "
                "Make sure host is reachable."))

    if path := split.path.strip('/'):
        return f'{scheme}://{host}:{port}/{path}'

    return f'{scheme}://{host}:{port}'