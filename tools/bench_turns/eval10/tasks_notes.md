# Eval 10 scenario notes

Hosts: datatables.net, books.toscrape.com, www.scrapethissite.com, oeis.org (4).

## Dropped
- timeanddate.com (3 scenarios): first verified by curl against result URLs (checks arithmetic only, and a solver could build the URL instead of driving the form); the site also rendered in Hindi for a default fetch, a determinism risk.
- gutenberg.org: down for maintenance.
- OEIS "Showing 1-N of M" counts: grow over time.
- scrapethissite Hockey Teams search: searching "New" returns only 4 rows with no pagination, so it did not exercise paging; replaced by the Oscar AJAX page.
- datatables.net sort direction: my first script clicked Salary twice and got ascending order, so the prompt asks for the highest salary rather than naming a sort direction.

## Driven in a real browser (Playwright/Chromium, en-US, from the start URL, no constructed query strings)
- S1: examples index -> Basic Initialisation -> Zero configuration; select 25, search "Software Engineer", sorted by Salary. Saw 6 rows, top salary $206,850 Brenden Wagner (San Francisco).
- S2: home -> Mystery -> next page (page-2) -> "The Silkworm (Cormoran Strike #2)" (5 stars, £23.05, higher than The Girl You Lost £12.29). Detail table showed UPC f06039c29b5891fa. Availability varies, so it is not asked.
- S3: home -> Sandbox -> Oscar Winning Films -> 2010 (max awards 4: The King's Speech, Inception) and 2013 (Gravity 7). Answer Gravity. Content loads via AJAX after the click.
- S4 and S5 (OEIS) were kept unchanged as instructed; those two were verified earlier by curl on the search results only and not driven in a browser by me.
