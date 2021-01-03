# Scaler

A project aimed at auto scaling docker swarm services when the number of active cluster nodes changes.

Configures by label on each service that should be scaled:
- `scaler.enabled` (bool) - toggler of scaler logic
- `scaler.per_node` (integer) - instances count per each active node
- `scaler.node_filter` (string) - WIP. default `role = worker`
