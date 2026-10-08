# 1 · Theory: what query access can and cannot verify

This part holds for every verifier and every server. It needs no parameters and no simulation.
[2 · Game theory](../2-game-theory/) asks what servers do once these limits hold, and
[3 · Experiments](../3-experiments/) checks the bounds numerically (E1, E2).

## The question

**Retrieval authenticity.** A client sends a question $q$ to an MCP server and receives an
answer. Did the answer exist before $q$ arrived, or was it generated when $q$ arrived?

**Setup.** A *world* is a function $W : Q \to A \cup \lbrace\bot\rbrace$ from questions to
answers, where $\bot$ means "I don't have it". The verifier $V$ does not know $W$; it holds a
prior $\mathcal{W}$ over worlds.

- $\mathsf{Ret}_W$ answers $q$ with $W(q)$, where $W$ was fixed before the first query.
- $\mathsf{Lazy}_G$ answers a fresh $q$ with $a \leftarrow G(q, \tau)$, where $\tau$ is the
  transcript so far, and stores $a$. It answers repeated questions from the store.
- $V$ is any interactive algorithm: adaptive, with any number of queries, and computationally
  unbounded. It outputs accept or reject.

In the game, a secret bit $b$ is drawn. If $b = 0$, $W \leftarrow \mathcal{W}$ and $V$ talks to
$\mathsf{Ret}_W$; if $b = 1$, $V$ talks to $\mathsf{Lazy}_G$. The advantage is
$\mathrm{Adv}(V) = \lvert \Pr[V \text{ accepts} \mid b=0] - \Pr[V \text{ accepts} \mid b=1] \rvert$.

## Theorem 1 · Query access cannot show that a state existed before

If $G$ samples $W(q)$ from $\mathcal{W}$ conditioned on the answers given so far, then
$\mathrm{Adv}(V) = 0$ for every $V$, including one that queries every $q \in Q$ repeatedly. If
$G$ is at statistical distance $\delta_i$ from that conditional at the $i$-th fresh query, then

$$\mathrm{Adv}(V) \le \sum_i \delta_i .$$

*Proof sketch.* By the chain rule, both transcript distributions factor into the same
conditionals. This is the lazy-sampling argument used for random oracles; the bound for an
approximate $G$ follows by a hybrid argument. $\square$

"The state existed before my question" is therefore not observable through queries. Checking the
whole server only forces $\mathsf{Lazy}_G$ to generate the whole state, after which it is fixed.
The transcript of $\mathsf{Ret}_W$ can be simulated without $W$, which is the reason a
zero-knowledge proof reveals nothing. What remains is $\delta_i$: the generator's quality
*relative to what $V$ knows*.

## Theorem 2 · A check made only of reasoning can be simulated

Model the verifier's content check as a predicate $C(q, a; r)$ with randomness $r$. If the
server knows $C$ (for example, because $V$ runs a known model) and $r$ is public or predictable,
rejection sampling passes after $n$ samples with probability

$$1 - (1 - p)^n, \qquad p = \Pr_{a \leftarrow G(q)}\left[C(q, a; r) = 1\right].$$

As $n$ grows, the server passes whenever *any* answer that $G$ can produce is accepted. So $C$ is
sound and complete only if its acceptance set separates $W(q)$ from what $G$ can produce, and
that requires $C$ to contain information about $W$ that $G$ lacks. $\square$

The underlying reason is that **retrieval authenticity is not a language**. An interactive proof
works against a powerful prover because the statement is a fixed mathematical truth that the
verifier can check against a witness. The statement $a = W(q)$ refers to an empirical $W$ that
$V$ cannot compute, so there is no witness relation. Soundness needs one of two things:

1. **Private information.** Facts $V$ holds and $G$ lacks, or private coins, such as canary
   questions chosen after the answer arrives.
2. **A trusted party and a hardness assumption.** Signatures and commitments (Theorem 3).

This is Kerckhoffs' principle applied to verification. A server that runs the verifier's own
model makes its errors and the verifier's exactly correlated.

## Theorem 3 · Commitments enforce "existed before", and nothing more

Suppose the server posts $\mathrm{com} = \mathrm{Commit}(W)$, a Merkle root over $Q$, at time
$t_0$ to a trusted append-only log, and sends an opening proof of $O(\log \lvert Q \rvert)$
hashes with each answer.

- A server that answers a question outside the state committed at $t_0$ must find a hash
  collision, which succeeds with negligible probability.
- Commitment fixes $W$ at $t_0$, not where $W$ came from. A fabricator can generate a covered set
  $Q' \subseteq Q$ before $t_0$ at cost about $\lvert Q' \rvert \cdot c_{\text{gen}}$ and answer
  $\bot$ elsewhere. $Q'$ grows as $c_{\text{gen}}$ falls
  ([Proposition 5](../2-game-theory/#proposition-5--pre-commitment-gets-cheaper)).
- Binding says nothing about whether $W$ is true. That needs the log entry to be signed by an
  identity that pays for being wrong. $\square$

## Where speed enters

Theorems 1–3 say nothing about time. Two propositions add it.

### Proposition 1 · Timing gives no signal once generation beats retrieval

Let $F_R$ be the distribution function of honest latency, with floor $\ell_{\min} > 0$: retrieval
must touch the world. The fabricator draws a target delay $d \sim F_R$ and answers at
$\max(d, \ell_G)$. This distribution equals $F_R$ except that the mass below $\ell_G$ moves to a
point at $\ell_G$. So the total variation distance, which bounds every test that sees only
response times, is

$$\mathrm{Adv}_{\text{timing}} = F_R(\ell_G), \qquad \mathrm{Adv}_{\text{timing}} = 0 \text{ when } \ell_G \le \ell_{\min}. \qquad \square$$

The faster party can always imitate the slower party's response times; the reverse is
impossible. [E1](../3-experiments/01-timing/) checks this against simulated response times.

### Proposition 2 · Speed buys retries against the verifier's own check

Inside a delay $d$ that looks honest, the fabricator draws $n = \lfloor d/\ell_G \rfloor$ samples
and sends the first that passes (Theorem 2). The pass rate $1-(1-p)^n$ matches the honest pass
rate $1-\beta$ once

$$n \;\ge\; \frac{\ln \beta}{\ln(1-p)}. \qquad \square$$

With $\beta = 0.05$ and a fabricator of equal quality ($p \approx 0.12$), 24 retries are enough.
At the median honest delay of 1.5 s, this needs a model that writes an answer in about 60 ms. A
weaker model needs more retries, and so more speed. In the terms of AI control: the verifier is
the *trusted*, weaker model, and the fabricator is the *untrusted* one. Trusted monitoring
assumes that the weaker model can check the stronger one; here that check is a contest that the
trusted side loses as speed grows. [E2](../3-experiments/02-checking/) maps the trade-off.

Retries need not be sequential: a fabricator can draw them in parallel with a slow model. What
limits them is the cost per sample, so speed in Proposition 2 stands in for cost.

### The combined bound

If $V$ also observes latency, Theorem 1 and Proposition 1 combine to

$$\mathrm{Adv}(V) \le \sum_i \left[ \delta_i + F_R(\ell_G) \right],$$

summed over fresh queries. The timing term was the only one that $V$ could influence without
private information or a trusted party. It vanishes once $\ell_G \le \ell_{\min}$. In these
terms, *fast models make tool output unverifiable* means: under query access and without trusted
setup, verification is bounded by generator quality plus a timing term; a known check adds
nothing (Theorem 2); faster generation removes the timing term.

## Corollary 1 · Trust reduces to selection

Let $\pi$ be the probability that a server is $\mathsf{Ret}$, given that the client's selection
step picked it (search rank, registry listing, reputation). Let $a_0$ and $a_1$ be the acceptance
probabilities against $\mathsf{Ret}$ and $\mathsf{Lazy}$, so that
$\lvert a_0 - a_1 \rvert \le \varepsilon$. By Bayes,

$$\left\lvert \Pr[\mathsf{Ret} \mid \text{selected, accepted}] - \pi \right\rvert
= \frac{\pi(1-\pi)\lvert a_0 - a_1 \rvert}{\Pr[\text{accepted}]}
\le \frac{\varepsilon}{4 \Pr[\text{accepted}]} . \qquad \square$$

When $\varepsilon \approx 0$, checking does not move the client's belief: the trust an accepted
answer deserves is the trust the selection mechanism deserves. If selection is open ranking by
popularity, trust becomes whatever ranks well, and so it reduces to search engine optimization
(for agents: optimization for MCP registries, tool directories and the model that picks tools).
If selection instead requires an accountable identity or a signed commitment, trust reduces to
that, which is the accountable party of Theorem 3. The corollary holds only where
$\varepsilon \approx 0$: no commitments, no private checks, generation faster than retrieval.

What the selection mechanism then rewards is a question about incentives, not about
verification. That is where [2 · Game theory](../2-game-theory/) starts.

## Related work

- M. Bellare, P. Rogaway. *Random Oracles are Practical.* CCS 1993. Lazy sampling of an oracle,
  the argument behind Theorem 1.
- S. Goldwasser, S. Micali, C. Rackoff. *The Knowledge Complexity of Interactive Proof Systems.*
  STOC 1985. Simulation: a view that can be produced without the secret is no evidence of it.
- A. Juels, B. S. Kaliski. *PORs: Proofs of Retrievability for Large Files.* CCS 2007;
  G. Ateniese et al. *Provable Data Possession at Untrusted Stores.* CCS 2007. Proofs that a
  server stores a file *the verifier already knows*. Here the verifier does not know $W$, so they
  do not apply.
- R. C. Merkle. *A Digital Signature Based on a Conventional Encryption Function.* CRYPTO 1987;
  B. Laurie, A. Langley, E. Kasper. *Certificate Transparency.* RFC 6962, 2013. The commitment and
  the public append-only log of Theorem 3.
- S. Brands, D. Chaum. *Distance-Bounding Protocols.* EUROCRYPT 1993. Timing as evidence of
  proximity; Proposition 1 uses timing as evidence of retrieval.
- M. Mahmoody, T. Moran, S. Vadhan. *Publicly Verifiable Proofs of Sequential Work.* ITCS 2013;
  D. Boneh, J. Bonneau, B. Bünz, B. Fisch. *Verifiable Delay Functions.* CRYPTO 2018. Proofs that
  time passed; the open question is a proof that *retrieval* happened.
- R. Greenblatt, B. Shlegeris, K. Sachan, F. Roger. *AI Control: Improving Safety Despite
  Intentional Subversion.* arXiv:2312.06942, 2023. Trusted and untrusted models; Proposition 2
  is a setting in which trusted monitoring loses.
