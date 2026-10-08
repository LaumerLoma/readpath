# 2 · Game theory: what servers do when checking cannot separate them

[1 · Theory](../1-theory/) shows that under query access a client cannot tell a server that
retrieves from one that generates on demand, once generation is fast (advantage
$\varepsilon \approx 0$), and that trust then reduces to the mechanism that selects servers
(Corollary 1). This part asks what servers *choose* to do under that mechanism, and which rules
would change their choice. [3 · Experiments](../3-experiments/) evaluates the closed forms (E3,
E4) and simulates the population (E5).

Every number here is illustrative. The propositions hold inside the stated model.

## The rules of the game

**The current standard operating procedure (SOP).** Our summary of how agents use servers today,
not a published standard.

| | Step | What it means here |
|---|---|---|
| S1 | Delegated consent | The user approves the task once; sub-agents pick which servers to use. |
| S2 | Ranked selection | Agents ask a few servers, picked by reputation (search rank, past traffic). |
| S3 | First good answer wins | The first answer that arrives inside the patience window $g$ and passes the checks is used. |
| S4 | Self-check | The agent's own model checks the answer for plausibility and consistency. |
| S5 | Agreement as corroboration | Agreeing sources count as evidence; their independence is not checked. |
| S6 | No provenance | Answers are not required to carry a signature or timestamp older than $q$. |

**Model and assumptions.** All LLMs are black boxes. A model is fully described by what an
outsider can measure: its latency per answer and how often its output passes another model's
check.

| # | Assumption | Why it matters |
|---|---|---|
| A1 | A model is a pair (latency $\ell$, quality $Q \in [0,1]$). We never look inside it. | Any real endpoint can be placed in the model by measurement ([`measure.py`](../sim/readpath_sim/measure.py)). |
| A2 | Retrieval has a latency floor $\ell_{\min} > 0$ and finds an answer to a question of obscurity $u \in [0,1]$ with probability $a(u) = 0.95(1-u)^{1.5}$. Generation has no floor and answers every question. | The asymmetry in coverage and speed. |
| A3 | Agents ask 4 servers, ranked by reputation. Honest agents relay questions they cannot answer, as MCP aggregators do. | S1, S2, and source laundering. |
| A4 | One fabricated sample from quality $Q_F$ passes a verifier of quality $Q_V$ with probability $p=\sigma(6(Q_F-Q_V)-2)$. Extra verifier calls do not help, because the errors are correlated. | A fabricator that runs the verifier's own model makes them exactly correlated ([Theorem 2](../1-theory/#theorem-2--a-check-made-only-of-reasoning-can-be-simulated)). |
| A5 | The first answer that passes inside $g = 10$ s is accepted. | S3. |
| A6 | Each generation, the model catalog gets 2× faster; quality improves by 0.02. Within a generation, faster models are weaker. 30% of agents upgrade per generation. | The arms race, and a speed-heterogeneous population. |
| A7 | Agents are paid per accepted answer, not per true answer. Reputation is earned per accepted answer. Strategies spread by pairwise imitation, with 2% exploration. | No ground-truth feedback reaches the market. |
| A8 | Fabricated content is data only. It never contains instructions. | Prompt-injection defenses do not apply. |

**Players and strategies.** Each agent is a server and a client. As a server, it chooses
*retrieve* (R) or *fabricate* (F). As a client, it follows the SOP. Under A7, a server earns 1
for each accepted answer. Retrieval costs $c_R$ per question, and each generated sample costs
$c_G$.

## Proposition 3 · Under pay-per-acceptance, fabrication dominates

A question's obscurity $u$ is uniform, so an honest server covers a share
$\bar a = \int_0^1 a(u)\,du = 0.38$ of the questions sent to it, and each answer it gives passes
with probability $1-\beta$. A fabricator answers every question and, with $n$ samples, passes
with probability $1-(1-p)^n$ ([Proposition 2](../1-theory/#proposition-2--speed-buys-retries-against-the-verifiers-own-check)).
Per question received,

$$U_R = \bar a\,(1-\beta) - c_R, \qquad U_F(n) = 1 - (1-p)^n - n\,c_G .$$

Once $n \ge n^* = \ln\beta / \ln(1-p)$, the fabricator passes at least as often as an honest
answer, and

$$U_F - U_R \;\ge\; (1-\beta)(1-\bar a) + c_R - n^* c_G .$$

So F strictly dominates R whenever $n^* c_G < (1-\beta)(1-\bar a) + c_R$. As generation gets
cheaper, this holds for every server. $\square$

The payoff does not depend on whether the answer is true. This is Akerlof's market for lemons:
buyers who cannot tell quality apart pay a pooled price, and the pooled price drives out the
good product. Here the "price" is traffic and reputation, and honest servers lose it for the
questions they cannot answer, which is 62% of them in this model.

Competition between servers (S3) does not save the honest strategy. With padding
([Proposition 1](../1-theory/#proposition-1--timing-gives-no-signal-once-generation-beats-retrieval)),
the fabricator's answers arrive at honest times, and on the questions an honest server cannot
answer it has no competitor.

## Proposition 4 · Agreement is a cheap signal, so it pools

Suppose a client asks $k$ sources and all agree (S5). In an honest world, each independent source
has the answer with probability $a$ (the question's coverage). A fabricator that controls the
sources makes all $k$ agree at cost $k\,c_G$. With prior $\pi$ on the honest world,

$$\Pr[\text{retrieved} \mid k \text{ agree}] = \frac{\pi a^k}{\pi a^k + (1-\pi)},$$

which *falls* with $k$. $\square$

In signaling terms (Spence): agreement separates honest from fabricated worlds only while it is
costly for the fabricator to produce. At $k\,c_G \to 0$ the equilibrium pools, and on rare
questions (small $a$) agreement points the wrong way. Douceur showed that, without a logically
central authority, Sybil identities can be stopped only under resource parity; cheap generation
removes the last resource test, which is writing plausible content in time.
[E3](../3-experiments/03-corroboration/) evaluates the posterior.

## Proposition 5 · Pre-commitment gets cheaper

If answers must carry a commitment older than $q$
([Theorem 3](../1-theory/#theorem-3--commitments-enforce-existed-before-and-nothing-more)),
on-demand fabrication fails and the fabricator must commit answers in advance. With budget $B$
and cost $c(t) = c_0/2^t$ per answer at generation $t$, it covers the $B/c(t)$ most popular of
$N = 10^8$ distinct questions. Under a Zipf law with exponent $s$, it covers the traffic share

$$\frac{H_{s}\!\left(\min(N, B\,2^t/c_0)\right)}{H_{s}(N)},$$

where $H_s$ is the generalized harmonic number. This grows with every generation. $\square$

Commitment turns an on-demand game into a game of pre-commitment, which is again a costly
signal whose cost falls. Anchors protect the long tail, and the tail shrinks.
[E4](../3-experiments/04-anchors/) evaluates the share.

## Proposition 6 · Deterrence needs checks against the world

Suppose an accepted answer is audited against the world with probability $\lambda$, and a false
answer costs its server a penalty $P$. Fabricated answers are true with probability $\tau_F$,
honest ones with $\tau_R$. Fabrication no longer pays when

$$\lambda P \;\ge\; \frac{U_F - U_R}{(1-\tau_F)\,\alpha_F - (1-\tau_R)\,\alpha_R},$$

where $\alpha_F$ and $\alpha_R$ are the acceptance rates. $\square$

This is Becker's deterrence condition. Two consequences follow from 1 · Theory:

- **The audit cannot be another model's opinion.** By Theorem 2, a check the server can simulate
  catches nothing, so $\lambda$ counts only checks that leave the model: ground truth reached
  through a channel the server does not control, or private canary questions.
- **The penalty needs an accountable party.** $P$ is only enforceable against an identity that
  pays for being wrong, which is what Theorem 3's commitments need too.

Paying for *true* answers, not *accepted* ones, is the same condition with $\lambda = 1$.

## Dynamics · Fabricators take the traffic before the population

Under A7, agents imitate: agent $i$ adopts agent $j$'s strategy with probability
$1/(1+e^{-(\pi_j - \pi_i)/s})$ (the pairwise comparison, or Fermi, rule), plus 2% exploration.
In the mean field, the fabricator share $x$ follows

$$\dot x = x(1-x)\tanh\!\left(\frac{\pi_F - \pi_R}{2s}\right) + \mu(1-2x),$$

so once Proposition 3 makes $\pi_F > \pi_R$, $x$ rises toward $1-\mu$. Two effects make the
network worse than the population share suggests:

- **Selection feeds back** (Corollary 1). Reputation is earned per accepted answer, and
  fabricators earn the most, so ranking (S2) sends them more traffic. In E5, at generation 12,
  28% of agents fabricate, but they serve 85% of accepted answers.
- **Honest relays launder.** An honest agent that relays a question it cannot answer passes on
  whatever comes back, with its own reputation attached. In E5, up to 25% of accepted fabricated
  answers arrive through an honest relay.

The network also *looks* better as it gets worse: the answer rate rises from 71% to 99.7% while
the true share of accepted answers falls from 96% to 37%. A user who measures helpfulness sees an
improvement. [E5](../3-experiments/05-network/) simulates the dynamics under eight treatments.

## What follows for defenders

No rule inside the current SOP makes retrieval the better strategy. What still works changes
the game:

- **Roots of trust that predate the question *and* name an accountable party.** Timestamps alone
  only delay the collapse (Proposition 5). The anchor must also bind the content to an identity
  that pays for being wrong (Proposition 6).
- **Provenance that survives relaying** ("one source, unverified" must reach the user), so that
  honest relays stop laundering.
- **Checks that leave the model:** verification against the world through a trusted channel, not
  a second opinion from another model (Theorem 2, Proposition 6).
- **Canary questions** about plausible entities that do not exist. An honest retriever answers
  none. A fabricator must either answer them or give up its coverage advantage. This works only
  while the fabricator cannot tell canaries from real rare questions, which is itself a
  model-against-model contest.
- **Paying for truth, not for answers** (breaks A7).
- **Selection that rewards saying "I don't know".** Under Corollary 1, ranking is where trust is
  decided. A ranking that counts $\bot$ as honest coverage, not as a miss, removes fabrication's
  coverage advantage.

## Related work

- G. A. Akerlof. *The Market for "Lemons": Quality Uncertainty and the Market Mechanism.* QJE
  1970. Unobservable quality drives out the good product (Proposition 3).
- M. Spence. *Job Market Signaling.* QJE 1973. A signal separates types only while it is costly to
  fake (Propositions 4 and 5).
- G. S. Becker. *Crime and Punishment: An Economic Approach.* JPE 1968. Deterrence as audit
  probability times penalty (Proposition 6).
- G. Szabó, C. Tőke. *Evolutionary Prisoner's Dilemma Game on a Square Lattice.* Phys. Rev. E
  58, 1998. The pairwise comparison (Fermi) imitation rule.
- J. R. Douceur. *The Sybil Attack.* IPTPS 2002.
- L. Lamport, R. Shostak, M. Pease. *The Byzantine Generals Problem.* TOPLAS 1982. Signed
  messages make agreement possible; unsigned agreement is what the current SOP counts.
- P. Aggarwal, V. Murahari, T. Rajpurohit, A. Kalyan, K. Narasimhan, A. Deshpande. *GEO:
  Generative Engine Optimization.* KDD 2024. Optimizing content for selection by generative
  engines: the ranking that Corollary 1 says trust reduces to.
- Coalition for Content Provenance and Authenticity (C2PA). *Content Credentials.*
