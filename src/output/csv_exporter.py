import csv
import os
from .data_exporter import DataExporterBase

class BasicCsvExporter(DataExporterBase):
    def __init__(self, filename):
        self.filename = filename
        self.existing = set()
        # Create directory if it doesn't exist
        output_dir = os.path.dirname(self.filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        # Create file and write header if it doesn't exist
        if not os.path.exists(self.filename):
            with open(self.filename, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=self.fieldnames)
                writer.writeheader()

    fieldnames = [
        'id', 'description', 'vendor', 'cwe_category', 'cwe_explanation', 
        'cause', 'impact', 'published', 'cvss_score', 'severity', 'source', 
        'description_without_punct', 'description_normalized', 'explanation'
    ]

    def write_row(self, row):
        if 'id' not in row or not row['id']:
             #print("Warning: Row without 'id':", row)
            return
        # Append row to file.
        with open(self.filename, 'a', newline='', encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerow(row)

    def export(self, data):
        for item in data:
            if item.get('id') not in self.existing:
                self.write_row(item)