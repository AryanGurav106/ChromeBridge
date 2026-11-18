# Eval 10 scenario notes

Verified by fetching the underlying pages/queries with curl (English Accept-Language); not driven in a browser.
- S1: durationresult 14 Mar 2015 -> 2 Nov 2019, end date included: 1695 days.
- S2: dateadded 1 Jan 2020 + 1000 days = 27 Sep 2022 (Tuesday, computed).
- S3: Reykjavik June 2019 row 21: sunrise 02:55 (sunset column reads 00:03, next day).
- S4: A000041 a(30)=5604; S5: A000108 a(15)=9694845 (both checked against the formulas/data lines).

Dropped:
- gutenberg.org (planned search/filter scenario): site down for maintenance when checked.
- timeanddate holidays by country (e.g. Canada 2019 Thanksgiving): date text is locale-dependent (fetched page rendered in Hindi), so the answer string is not stable; replaced by numeric/weekday answers.
- OEIS result counts ("Showing 1-N of M"): change as the database grows, not deterministic.

Caveats: timeanddate may render dates in a locale-dependent format; S2 asks for the English weekday, which should be stable. Only 2 hostnames needed.
