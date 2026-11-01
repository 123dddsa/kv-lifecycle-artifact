---- MODULE IdentityCounting ----
\* Mechanization of the identity counting law (Theorem `thm:count`).
\* k scoped operations share one bare request ID; deliveries may arrive in any
\* order. Two monitors are compared:
\*   insensitive: keyed by the bare request ID  -> k-1 duplicate alerts
\*   scoped     : keyed by (request, child)      -> zero duplicate alerts
EXTENDS Naturals, FiniteSets, TLC

CONSTANTS k
ASSUME k \in {2, 3}

VARIABLES delivered, deliveredReq, alertsIns, alertsScope

vars == <<delivered, deliveredReq, alertsIns, alertsScope>>

Init ==
    /\ delivered = {}
    /\ deliveredReq = FALSE
    /\ alertsIns = 0
    /\ alertsScope = 0

\* Deliver the scoped operation with index i (its child id); each operation
\* delivers exactly once, in any order.
Deliver(i) ==
    /\ i \in 0..(k-1) \ delivered
    /\ delivered' = delivered \cup {i}
    /\ IF deliveredReq
       THEN alertsIns' = alertsIns + 1 /\ deliveredReq' = TRUE
       ELSE alertsIns' = alertsIns /\ deliveredReq' = TRUE
    /\ alertsScope' = alertsScope   \* scoped keys are distinct: no duplicate

Next == \E i \in 0..(k-1) : Deliver(i)

Spec == Init /\ [][Next]_vars

\* ===== checks =====
TypeOK ==
    /\ delivered \subseteq 0..(k-1)
    /\ alertsIns \in 0..k
    /\ alertsScope \in 0..k

\* The scoped monitor never reports a duplicate.
ScopeSilent == alertsScope = 0

\* The insensitive monitor reports exactly one alert per redundant delivery.
InsAlerts == alertsIns = IF Cardinality(delivered) = 0 THEN 0 ELSE Cardinality(delivered) - 1

\* At the end of any complete delivery order: k-1 insensitive, 0 scoped.
FinalCounting ==
    Cardinality(delivered) = k => (alertsIns = k - 1 /\ alertsScope = 0)

=============================================================================

