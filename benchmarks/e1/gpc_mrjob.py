"""E1 version A: transactions and amount per account and month from GPC statements, as an MRJob.

Run through `benchmarks.e1.run_e1` (`-r hadoop` on YARN). The mapper reads 075 records by their fixed
positions (docs/formats/gpc.md); amounts are signed as in Task 16 (booking 1 and 5 debit, 2 and 4 credit) and
kept in haléře until the reducer formats them as CZK. Imports only mrjob: YARN runs this file as it is.
"""

from mrjob.job import MRJob

SIGNS = {"1": -1, "2": 1, "4": 1, "5": -1}


def czk(haler: int) -> str:
    sign = "-" if haler < 0 else ""
    return f"{sign}{abs(haler) // 100}.{abs(haler) % 100:02d}"


class GpcMonthly(MRJob):
    # Daily statements are a few KB each: with the default input format every file is its own map task (4,216
    # on x10). Combining them into splits of up to 256 MB, as Hive's CombineHiveInputFormat does, compares the
    # engines instead of their handling of small files (that is E2).
    HADOOP_INPUT_FORMAT = "org.apache.hadoop.mapred.lib.CombineTextInputFormat"
    JOBCONF = {"mapreduce.input.fileinputformat.split.maxsize": "256000000"}

    def mapper(self, _, line):
        # Streaming passes "<offset>\t<line>" for CombineTextInputFormat (only the line for TextInputFormat);
        # GPC records have no tabs.
        line = line.rsplit("\t", 1)[-1].rstrip("\r")
        # Task 16 accepts booking codes 1, 2, 4 and 5 only: any other record is skipped (as in the HiveQL),
        # not a KeyError that fails the whole job.
        if not line.startswith("075") or len(line) != 128 or line[60] not in SIGNS:
            return
        account = str(int(line[3:19]))
        month = f"20{line[95:97]}-{line[93:95]}"
        amount = SIGNS[line[60]] * int(line[48:60])
        yield (account, month), (1, amount)

    def combiner(self, key, values):
        count = total = 0
        for n, amount in values:
            count += n
            total += amount
        yield key, (count, total)

    def reducer(self, key, values):
        count = total = 0
        for n, amount in values:
            count += n
            total += amount
        account, month = key
        yield None, (account, month, count, czk(total))


if __name__ == "__main__":
    GpcMonthly.run()
