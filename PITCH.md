# Maryada

Live RBI-conduct coach for loan-recovery calls

## Problem
Recovery calls are usually reviewed after they end, when a bad line has already been said and the borrower has already heard it. Agents get no help in the moment, and managers hear about problems late. RBI's new conduct rules for recovery agents (RBI/2026-27/223, issued 6 August 2026) apply from 1 January 2027. They include no threats or humiliation, contact only between 8 AM and 7 PM, and more.

## Who it is for
- Loan-recovery agents, who use it live during the call.
- Their managers, who see how the team is doing.
- Lender compliance teams.

## Solution
Maryada listens to the call as it happens, one agent turn at a time. When a line breaks a rule, it flags that line within seconds, names the rule, and speaks a short coaching nudge into the agent's headset. After the call, the agent gets a report and managers get a team view across agents. The agent sees the exact words that broke the rule, the reason, and a polite alternative to say instead.

## Gnani AI models used
- **Gnani Prisma V3.0**: speech to text. It turns each agent turn into text for the rule check.
- **Gnani Timbre V3.0**: text to speech. It voices the coaching nudges and the synthetic call audio.

Rule checking uses phrase rules plus a language-model check with **gpt-5.4-mini**.

## Results
Measured on 30 synthetic calls with 35 labelled issues, full engine, clean audio:
- Precision 75.0% (30 of 40 flags).
- Recall 85.7% (30 of 35 issues).

The 10 extra flags are counted against the score. One reviewer, the author, judged 3 of them real, 3 unsure and 4 not a violation. With phone-line noise added, recall stayed at 88.6% at 5 dB, but precision fell to 56.4%, mainly because the lender-name rule mishears the name.

All calls are synthetic. Nothing was tested on real calls. This is a demo, not legal advice.

## My contribution
Built solo by Vineet Patel: the rule engine, the live coaching, the call report and manager view, and the evaluation.

## Links
- Live demo: https://maryada.aiwithvineet.in
- Repository: https://github.com/vineet416/maryada-call-coach
- Full walkthrough video: coming soon
