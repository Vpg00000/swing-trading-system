# Event research -- confirmed price+volume moves

The mechanical layer (engine/news.py) confirmed these moves (>=3% price
move on >=1.5x average volume) and engine/priced_in.py compared each to the
stock's own historical comparable-event drift:

{event_flags}

## Priced-in quantitative read (our own price history, not news)

{priced_in_results}

For each stock:
1. What happened? Search NSE/BSE filings and Tier 1 sources first.
2. Economic significance -- real fundamental change, or noise?
3. Given the quantitative priced-in read above, does your news read change
   or confirm that assessment? (e.g. a "LIKELY_PRICED_IN" quantitative
   status paired with a genuinely new, larger-than-usual catalyst might
   still be actionable -- say so if you find that.)
4. Is this still actionable at the current price?
5. Classify source tier per system_prompt.md's hierarchy.

Follow the output contract in system_prompt.md.
