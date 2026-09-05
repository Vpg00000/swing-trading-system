try:
    from src.system_health import task_safety
except Exception:
    task_safety = None

from data.database import get_system_health_records
from engine.resiliency import get_overall_system_state

def get_system_health_data():
    return aggregate_system_health()

def verify_system_health():
    if task_safety is None:
        return
    task_safety.execute_flow('fii')
    task_safety.execute_flow('dii')
    task_safety.execute_flow('mf')
    task_safety.execute_flow('insider')
    task_safety.execute_flow('bulk')
    task_safety.execute_flow('block')
    task_safety.execute_flow('promoter')

def aggregate_system_health():
    records = get_system_health_records()
    overall_status = get_overall_system_mode(records)
    aggregated_data = {
        'overall_status': overall_status,
        'components': records
    }
    return aggregated_data

def get_component_status(component):
    if component['status'] == 'OK':
        return 'OK'
    elif component['status'] == 'STALE':
        return 'STALE'
    elif component['status'] == 'ERROR':
        return 'ERROR'
    elif component['status'] == 'UNAVAILABLE':
        return 'UNAVAILABLE'
    elif component['status'] == 'DEGRADED':
        return 'DEGRADED'
    else:
        return 'UNKNOWN'

def get_overall_system_mode(components):
    statuses = [get_component_status(component) for component in components]
    if 'ERROR' in statuses or 'UNAVAILABLE' in statuses:
        return 'TRADING_BLOCKED'
    elif 'STALE' in statuses or 'DEGRADED' in statuses:
        return 'DEGRADED'
    elif 'OK' in statuses:
        return 'NORMAL'
    else:
        return 'UNKNOWN'

if __name__ == "__main__":
    verify_system_health()
    health_data = aggregate_system_health()
    print(health_data)