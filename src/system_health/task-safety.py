class TaskSafetyStateMachine:
    def __init__(self):
        self.current_state = 'initial'

    def verify_fii(self):
        if self.current_state == 'initial':
            self.current_state = 'fii_verified'
            return True
        return False

    def verify_dii(self):
        if self.current_state == 'fii_verified':
            self.current_state = 'dii_verified'
            return True
        return False

    def verify_mf(self):
        if self.current_state == 'dii_verified':
            self.current_state = 'mf_verified'
            return True
        return False

    def verify_insider(self):
        if self.current_state == 'mf_verified':
            self.current_state = 'insider_verified'
            return True
        return False

    def verify_bulk(self):
        if self.current_state == 'insider_verified':
            self.current_state = 'bulk_verified'
            return True
        return False

    def verify_block(self):
        if self.current_state == 'bulk_verified':
            self.current_state = 'block_verified'
            return True
        return False

    def verify_promoter(self):
        if self.current_state == 'block_verified':
            self.current_state = 'promoter_verified'
            return True
        return False

    def reset(self):
        self.current_state = 'initial'

# Example usage in system_health.py
from task_safety import TaskSafetyStateMachine

def check_task_safety():
    state_machine = TaskSafetyStateMachine()
    if state_machine.verify_fii() and state_machine.verify_dii() and state_machine.verify_mf() and state_machine.verify_insider() and state_machine.verify_bulk() and state_machine.verify_block() and state_machine.verify_promoter():
        print("Task safety verified")
    else:
        print("Task safety verification failed")
        state_machine.reset()