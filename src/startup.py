"""Local server startup, storage preflight and existing-instance detection."""
import argparse
import http.client
import json
import os
import uuid
from research_search import external_directory, private_directory, SafeError
from verification_models import digest


def storage_preflight(base):
    base = external_directory(base)
    path = base / ('write-probe-' + uuid.uuid4().hex)
    created = False
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            stream.write(b'private storage preflight')
            stream.flush()
            os.fsync(stream.fileno())
        path.unlink()
        created = False
    except OSError:
        raise SafeError('Private folder is not writable. Check folder permissions, free disk space, and whether the launcher is running in a restricted environment.') from None
    finally:
        if created:
            try:
                path.unlink()
            except OSError:
                pass
    return base


def existing_server(port):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request('GET', '/health')
        response = connection.getresponse()
        data = response.read(4097)
        if response.status == 200 and len(data) <= 4096:
            value = json.loads(data)
            if isinstance(value, dict) and value.get('application') == 'technical-research-engine':
                return value
        return {'other_service': True}
    except ConnectionRefusedError:
        return None
    except (OSError, ValueError, http.client.HTTPException):
        return {'other_service': True}
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', help='Existing private folder outside Git; overrides environment.')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    try:
        base = external_directory(args.data_dir) if args.data_dir else private_directory()
        base = storage_preflight(base)
        running = existing_server(args.port)
        if running is not None:
            if running.get('configured') and running.get('storage_id') == digest(str(base)):
                print(f'Engine already running: http://127.0.0.1:{args.port}. Reuse it; no second server started.')
                return 0
            raise SafeError('Port is already occupied by another or older server, or a different private folder. Stop that server or choose --port; no process was terminated.')
        from ui_service import Application
        from ui import create_server
        app = Application(base)
        try:
            server = create_server(args.port, app)
        except OSError:
            raise SafeError('Port became unavailable. Stop the existing server or choose --port.') from None
        print(f'Open http://127.0.0.1:{args.port} - storage checked; Ctrl+C stops the server.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except SafeError as exc:
        print(str(exc))
        return 2
    except OSError:
        print('Unable to start: check access to private storage and application files.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
