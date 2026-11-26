Thanks — this is a thorough review and a fair replication. Agreed on merging it as the probe-only measurement: unset by default, nothing user-facing until a run passes on a second model.

The te3-small result reads clearly to me: neither checked arm passes the decisive pool there, each by one row, while the check still drops all 18 noise rows the plain margin adds — so the check holds on a second model even where the margin doesn't. That's the per-model variability the gate is meant to respect, and I'm glad you ran it blind.

The vector-cache-by-text point is a good catch — bge-m3's determinism masked it locally. Happy to see it as a separate follow-up rather than a change here. Looking forward to the rows and scripts landing in `results/issue121/`.