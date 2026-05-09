"""Classic pipeline shape — 4 stage classes in one package."""


class FileReader:
    def read(self, path): return open(path).read()


class JsonParser:
    def parse(self, text): return text


class RecordProcessor:
    def process(self, records): return records


class CsvWriter:
    def write(self, records): pass
