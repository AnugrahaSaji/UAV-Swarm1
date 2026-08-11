# sscheduler - Drone-controlled scheduler
# Reversed control: Drone schedules, GCS follows

# Additive swarm extension imports (backward compatible)
try:
    from swarm.swarm_manager import SwarmManager
    from swarm.leader import LeaderCoordinator
    from swarm.follower import FollowerAgent
    from swarm.heartbeat import HeartbeatManager
    from swarm.election import ElectionManager
    from swarm.trust_manager import TrustManager
    from swarm.membership_manager import MembershipManager
    from swarm.state_sync import StateSyncManager
    from swarm.recovery import RecoveryManager
    from swarm.messages import SwarmMessage
except Exception:  # pragma: no cover - import guard for optional extension
    SwarmManager = None
    LeaderCoordinator = None
    FollowerAgent = None
    HeartbeatManager = None
    ElectionManager = None
    TrustManager = None
    MembershipManager = None
    StateSyncManager = None
    RecoveryManager = None
    SwarmMessage = None
