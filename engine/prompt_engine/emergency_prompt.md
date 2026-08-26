# Emergency investigation -- {trigger_type}

An urgent-tier trigger has fired per DESIGN.md's notification/risk-control
rules (portfolio drawdown >8% from peak, Nifty -4%+ intraday, VIX >35, or a
stop gapped through).

## Trigger data

{trigger_data}

Investigate the cause as fast as possible using Tier 1 sources: is this a
broad market/macro event, a sector-specific shock, or symbol-specific?
Is there a knowable end-point (e.g. a scheduled policy announcement already
priced in) or is this open-ended risk? This is a fast, high-priority pass
-- report what you can verify now and flag what's still unknown rather than
waiting for full confirmation. Follow the output contract in
system_prompt.md. Remember: you do not decide the de-risk action -- Python
applies the hard emergency rule (e.g. halve equity exposure, cap at 10%);
your job is only to explain the *why* for the human reading the alert.
