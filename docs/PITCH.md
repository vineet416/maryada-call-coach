# Maryada

Live RBI-conduct coach for loan-recovery calls

Great Indian AI Internship Challenge | Gnani.ai. Synthetic demo, not legal advice.

Headline numbers (30 synthetic calls, clean audio): 30 of 35 labelled issues caught, 85.7% recall, 75.0% precision (30 of 40 flags).

## Problem
Recovery calls are usually reviewed after they end, when a bad line has already been said and the borrower has already heard it. Agents get no help in the moment, and managers hear about problems late. RBI's new conduct rules for recovery agents (RBI/2026-27/223, issued 6 August 2026) apply from 1 January 2027. They include no threats or humiliation, contact only between 8 AM and 7 PM, and more.

## Who it is for
- Loan-recovery agents, who use it live during the call.
- Managers, who see how the team is doing.
- Lender compliance teams.

## Solution
Maryada listens to the call as it happens, one agent turn at a time. When a line breaks a rule, it flags that line within seconds, names the rule, and speaks a short coaching nudge into the agent's headset. The agent sees the exact words that broke the rule, the reason, and a polite alternative to say instead. After the call, the agent gets a report and managers get a team view across agents.

## Gnani AI models used
- **Gnani Prisma V3.0**: speech to text. It turns each agent turn into text for the rule check.
- **Gnani Timbre V3.0**: text to speech. It voices the coaching nudges and the synthetic call audio.

Rule checks: phrase rules plus a **gpt-5.4-mini** check.

## Results
Measured on 30 synthetic calls with 35 labelled issues, full engine, clean audio:
- Precision 75.0% (30 of 40 flags).
- Recall 85.7% (30 of 35 issues).

The 10 extra flags are counted against the score. With phone-line noise added, recall stayed at 88.6% at 5 dB, but precision fell to 56.4%, mainly because the lender-name rule mishears the name.

All calls are synthetic and nothing was tested on real calls. This is a demo, not legal advice.

## My contribution
I built Maryada solo, covering the rule engine, live coaching, call report, manager view and evaluation. All design, rule and evaluation decisions are my own.

## Links
- Live demo: https://maryada.aiwithvineet.in
- Repository: https://github.com/vineet416/maryada-call-coach
- 3-minute walkthrough: https://youtu.be/-czfMx2bKXo
- LinkedIn post: https://lnkd.in/p/dN7GwkfM
