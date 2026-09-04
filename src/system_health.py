class SystemHealth:
    def __init__(self):
        self.status = 'UNKNOWN'
        self.last_refresh_time = None

    def update_status(self, source_status):
        if source_status == 'FRESH':
            self.status = 'HEALTHY'
        elif source_status == 'STALE':
            self.status = 'WARNING'
        elif source_status == 'ERROR':
            self.status = 'CRITICAL'
        elif source_status == 'PARTIAL':
            self.status = 'PARTIAL'
        self.last_refresh_time = datetime.now()

    def get_status(self):
        return self.status

    def get_last_refresh_time(self):
        return self.last_refresh_time

# Example usage
if __name__ == "__main__":
    health = SystemHealth()
    health.update_status('FRESH')
    print(f"Current Status: {health.get_status()}")
    print(f"Last Refresh Time: {health.get_last_refresh_time()}")