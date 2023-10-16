import os
import shutil

from django.apps import apps as django_apps

from edc_sync_files.ssh_client import SSHClientError

app_config = django_apps.get_app_config('edc_sync_files')


class MockSSHClient:

    def __init__(self, *args, **kwargs):
        self._connected = False
        self._username = kwargs.get('username', None)
        self._sftp_client = MockSFTPClient()

    def __enter__(self):
        self._connected = True
        return self

    def __exit__(self, type, value, traceback):
        self._connected = False

    def connect(self):
        self._connected = True

        return self

    def close(self):
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def open_sftp(self):
        return self._sftp_client

    def put(self, src, dst, callback=None, confirm=True):
        # Store the arguments used by the put method
        self._sftp_client.put(src, dst, callback, confirm)

    @property
    def put_args(self):
        return self._sftp_client.put_args

    def copy(self, filename=None):
        try:
            source_file = os.path.join(app_config.outgoing_folder, filename)
            destination_file = os.path.join(app_config.incoming_folder, filename)
            shutil.copy2(source_file, destination_file)
        except FileNotFoundError:
            return f'The file {filename} does not exist in the source directory.'
        except Exception as e:
            return 'An error occurred - ' + str(e)

    @property
    def username(self):
        return self._username


class MockSFTPClient:
    def __init__(self, *args, **kwargs):
        self._connected = False
        self._put_args = []
        self._progress_updates = []

    def close(self):
        self._connected = False

    def __enter__(self):
        self._connected = True
        return self

    def connect(self, ssh_conn=None):
        return self

    def __exit__(self, type, value, traceback):
        self._connected = False

    def put(self, src, dst, callback=None, confirm=True):
        # Store the arguments used by the put method
        shutil.copy2(src, dst)
        self._put_args.append((src, dst, callback, confirm))

    @property
    def put_args(self):
        return self._put_args

    def update_progress(self, progress, total):
        self._progress_updates.append((progress, total))

    @property
    def progress_updates(self):
        return self._progress_updates

    def rename(self, src, dst):
        # Mock rename operation: Do nothing or simulate behavior.
        shutil.copy2(src, dst)


class MockSSHClientWithError:

    def __init__(self, *args, **kwargs):
        self._connected = False
        self._sftp_client = MockSFTPClient()
        self.trusted_host = kwargs.get('trusted_host', None)

    def __enter__(self):
        self._connected = True
        return self

    def __exit__(self, type, value, traceback):
        self._connected = False

    def close(self):
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def open_sftp(self):
        return self._sftp_client

    def put(self, src, dst, callback=None, confirm=True):
        # Store the arguments used by the put method
        self._sftp_client.put(src, dst, callback, confirm)

    @property
    def put_args(self):
        return self._sftp_client.put_args

    def connect(self):
        if not self._connected:
            if not self.trusted_host:
                raise SSHClientError('Server \'127.0.0.1\' not found in known_hosts')
            else:
                raise SSHClientError('Authentication failed.')
        self._connected = True
        return self
