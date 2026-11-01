---- MODULE KVLifecycle ----
\* Single-request abstraction of the scoped KV lifecycle contract.
\* Two semantics are compared:
\*   Semantics = "separated": POLL observes and holds completions; DELIVER consumes.
\*   Semantics = "merged"   : POLL observes and consumes atomically (DELIVER removed).
\* The model mirrors <LOCAL_WORKSPACE>/search_pilot.py (the frozen model used by
\* the exact DP and the merged-oracle counterfactual in experiments/).
\*
\* Checks encoded for TLC:
\*   NoC1        : C1 (delivery after free) never fires
\*   MergedEmpty : under merged semantics no completion stays held at any state
\*   ViolationReachable is checked by looking for a NoC1 counterexample.

EXTENDS Naturals, TLC

CONSTANTS kappa, transport, Semantics, sendOutstanding
ASSUME kappa \in {"lmcache", "nixl"}
ASSUME transport \in {"DONE", "PROC"}
ASSUME Semantics \in {"separated", "merged"}
ASSUME sendOutstanding \in BOOLEAN

VARIABLES started, terminal, freed, pending, polled, sent, hS, hR, polls, violation

vars == <<started, terminal, freed, pending, polled, sent, hS, hR, polls, violation>>

Init ==
    /\ started = FALSE
    /\ terminal = FALSE
    /\ freed = FALSE
    /\ pending = FALSE
    /\ polled = FALSE
    /\ sent = FALSE
    /\ hS = FALSE
    /\ hR = FALSE
    /\ polls = 0
    /\ violation = FALSE

\* START creates the request and arms the first receive.
Start ==
    /\ started = FALSE
    /\ started' = TRUE
    /\ pending' = TRUE
    /\ UNCHANGED <<terminal, freed, polled, sent, hS, hR, polls, violation>>

\* ABORT marks the request terminal (the scheduler will free on a later consume).
Abort ==
    /\ started
    /\ terminal = FALSE
    /\ terminal' = TRUE
    /\ UNCHANGED <<started, freed, pending, polled, sent, hS, hR, polls, violation>>

\* The completion-production part of POLL (shared by both semantics).
PollFields ==
    LET done == pending /\ transport = "DONE"
        pending1 == pending /\ ~done
        polled1 == done \/ polled
        hR1 == done \/ hR
        ready == terminal /\ sent = FALSE
                 /\ ( (kappa = "lmcache" /\ polled1)
                      \/ (kappa = "nixl" /\ sendOutstanding) )
        hS1 == ready \/ hS
        sent1 == ready \/ sent
    IN
    <<pending1, polled1, hR1, hS1, sent1>>

\* Separated POLL: only observes; the completion stays held until DELIVER.
PollSeparated ==
    /\ Semantics = "separated"
    /\ started
    /\ LET r == PollFields
       IN /\ pending' = r[1]
          /\ polled' = r[2]
          /\ hR' = r[3]
          /\ hS' = r[4]
          /\ sent' = r[5]
          /\ polls' = polls + 1
          /\ UNCHANGED <<started, terminal, freed, violation>>

\* DELIVER consumes held completions; a delivery of a completion whose owner is
\* already released is the C1 violation. Freeing is triggered by consuming a
\* terminal receive or a send.
Deliver ==
    /\ Semantics = "separated"
    /\ (hS \/ hR)
    /\ violation' = (violation \/ (freed /\ (hS \/ hR)))
    /\ freed' = (freed \/ (terminal /\ hR) \/ hS)
    /\ hS' = FALSE
    /\ hR' = FALSE
    /\ UNCHANGED <<started, terminal, pending, polled, sent, polls>>

\* Merged POLL: observes and immediately delivers (observe happens before free).
PollMerged ==
    /\ Semantics = "merged"
    /\ started
    /\ LET r == PollFields
           hS1 == r[4]
           hR1 == r[3]
           delivered == hS1 \/ hR1
           violation1 == violation \/ (freed /\ delivered)
           freed1 == freed \/ (terminal /\ hR1) \/ hS1
       IN /\ pending' = r[1]
          /\ polled' = r[2]
          /\ hR' = FALSE
          /\ hS' = FALSE
          /\ sent' = r[5]
          /\ polls' = polls + 1
          /\ violation' = violation1
          /\ freed' = freed1
          /\ UNCHANGED <<started, terminal>>

Quiesce ==
    /\ started
    /\ UNCHANGED vars

Idle ==
    /\ started
    /\ UNCHANGED vars

Poll == PollSeparated \/ PollMerged

Next ==
    \/ Start
    \/ Abort
    \/ Poll
    \/ Deliver
    \/ Quiesce
    \/ Idle

Spec == Init /\ [][Next]_vars

\* ===== checks =====
NoC1 == violation = FALSE

\* Bound the poll counter so TLC explores a finite state space.
PollsBounded == polls <= 3

\* Under merged semantics no completion can stay held between steps.
MergedEmpty ==
    Semantics = "merged" => (hS = FALSE /\ hR = FALSE)

\* The separated semantics has a positive witness of length 6:
\* START, POLL, ABORT, DELIVER, POLL, DELIVER.
=============================================================================



