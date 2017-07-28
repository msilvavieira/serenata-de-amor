import csv
import lzma
import os
from concurrent.futures import ThreadPoolExecutor

from bulk_update.helper import bulk_update

from jarbas.core.management.commands import LoadCommand
from jarbas.core.models import Reimbursement


class Command(LoadCommand):
    help = 'Load Serenata de Amor receipts text dataset'
    count = 0

    def add_arguments(self, parser):
        super().add_arguments(parser, add_drop_all=False)
        parser.add_argument(
            '--batch-size', '-b', dest='batch_size', type=int, default=4096,
            help='Batch size for bulk update (default: 4096)'
        )

    def handle(self, *args, **options):
        self.queue = []
        self.path = options['dataset']
        self.batch_size = options['batch_size']
        if not os.path.exists(self.path):
            raise FileNotFoundError(os.path.abspath(self.path))

        self.main()
        print('{:,} reimbursements updated.'.format(self.count))

    def receipts(self):
        """Returns a Generator with batches of receipts text."""
        print('Loading receipts text dataset…', end='\r')
        with lzma.open(self.path, mode='rt') as file_handler:
            batch = []
            for row in csv.DictReader(file_handler):
                batch.append(self.serialize(row))
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
            yield batch

    def serialize(self, row):
        """
        Reads the dict generated by DictReader and returns another dict with
        the `document_id` and with data about the receipts text.
        """
        document_id = self.to_number(row.get('document_id'), cast=int)
        reimbursement_text = row.get('text')

        return dict(
            document_id=document_id,
            reimbursement_text=reimbursement_text,
        )

    def main(self):
        for batch in self.receipts():
            with ThreadPoolExecutor(max_workers=32) as executor:
                executor.map(self.schedule_update, batch)
            self.update()

    def schedule_update(self, content):
        document_id = content.get('document_id')
        try:
            reimbursement = Reimbursement.objects.get(document_id=document_id)
        except Reimbursement.DoesNotExist:
            pass
        else:
            reimbursement.reimbursement_text = content.get('reimbursement_text')
            self.queue.append(reimbursement)

    def update(self):
        fields = ['reimbursement_text', ]
        bulk_update(self.queue, update_fields=fields)
        self.count += len(self.queue)
        print('{:,} reimbursements updated.'.format(self.count), end='\r')
        self.queue = []
