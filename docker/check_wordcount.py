"""Word count used by docker/check.sh to prove that MapReduce runs on YARN (`-r hadoop`)."""

import re

from mrjob.job import MRJob

WORD = re.compile(r"\w+")


class CheckWordCount(MRJob):
    def mapper(self, _, line):
        for word in WORD.findall(line.lower()):
            yield word, 1

    def combiner(self, word, counts):
        yield word, sum(counts)

    def reducer(self, word, counts):
        yield word, sum(counts)


if __name__ == "__main__":
    CheckWordCount.run()
