import os
from .confirmation import Confirmation, ConfirmationError
from .constants import EXPORT_BATCH, SEND_FILES, CONFIRM_BATCH, PENDING_FILES
from .transaction import TransactionExporter, TransactionExporterError
from .transaction import TransactionFileSenderError, TransactionFileSender


class ActionHandlerError(Exception):
    pass


class ActionHandler:

    def __init__(self, **kwargs):
        self.data = {}
        self.using = kwargs.get('using')
        self.tx_exporter = TransactionExporter(
            export_path=kwargs.get('src_path'), **kwargs)
        self.history_model = self.tx_exporter.history_model
        self.confirmation = Confirmation(
            history_model=self.history_model, **kwargs)
        self.tx_file_sender = TransactionFileSender(
            history_model=self.history_model, **kwargs)
        self.sent_history = self.tx_exporter.history_model.objects.using(
            self.using).filter(sent=True).order_by('-sent_datetime')
        self.recently_sent_filenames = [
            obj.filename for obj in self.sent_history[0:20]]
        self.media_folder = kwargs.get('media_path')

    def action(self, label=None, **kwargs):
        self.data = dict(
            errmsg=None, batch_id=None,
            last_sent_files=[], last_archived_files=[],
            pending_files=[],
            confirmation_code=None)
        if label == EXPORT_BATCH:
            self._export_batch()
        elif label == SEND_FILES:
            self._send_files()
            self._send_media_files()
        elif label == CONFIRM_BATCH:
            self._confirm_batch()
        elif label == PENDING_FILES:
            pass
        else:
            raise ActionHandlerError(f'Invalid action. Got {label}')
        self.data.update(pending_files=self.pending_filenames)

    @property
    def pending_filenames(self):
        return [
            obj.filename for obj in self.tx_exporter.history_model.objects.using(
                self.using).filter(sent=False).order_by('-created') ]

    @property
    def media_filenames(self):
        ignore = ['.DS_Store', 'log.txt']
        filenames = []
        files = os.listdir(self.media_folder) if self.media_folder else None
        sent_files = self.sent_filenames()
        ignore.extend(sent_files)
        if files:
            filenames = [file for file in files if file not in ignore]
        return filenames

    def sent_filenames(self):
        sent = []
        media_path = '%(path)s/%(filename)s' % {'path': self.media_folder, 'filename': 'log.txt'}
        file = open(media_path, 'a+')
        file.seek(0)
        sent_files = file.readlines()
        for l in sent_files:
            sent.append(l.strip())
        return sent

    def _export_batch(self):
        try:
            batch = self.tx_exporter.export_batch()
        except TransactionExporterError as e:
            raise ActionHandlerError(e) from e
        else:
            if batch:
                self.data.update(batch_id=batch.batch_id)
                self.pending_filenames.append(batch.filename)

    def _send_files(self):
        try:
            filenames = self.tx_file_sender.send(
                filenames=self.pending_filenames)
        except TransactionFileSenderError as e:
            raise ActionHandlerError(e) from e
        else:
            self.data.update(
                last_sent_files=filenames, last_archived_files=filenames)

    def _send_media_files(self):
        try:
            filenames = self.tx_file_sender.send_media(
                filenames=self.media_filenames)
        except TransactionFileSenderError as e:
            raise ActionHandlerError(e) from e
        else:
            self.data.update(
                last_media_sent=filenames, last_archived_files=filenames)

    def _confirm_batch(self):
        try:
            code = self.confirmation.confirm()
        except ConfirmationError as e:
            raise ActionHandlerError(e) from e
        self.data.update(confirmation_code=code)
