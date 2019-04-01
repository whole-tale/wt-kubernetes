from .tasks_docker import DockerTasks
from .tasks_kubernetes import KubernetesTasks

class TasksFactory:
    def __init__(self):
        self.dict = {}
        self.dict['docker'] = DockerTasks
        self.dict['kubernetes'] = KubernetesTasks
    
    def getTasks(self, flavor):
        if flavor not in self.dict:
            raise Exception('Unsupported tasks flavor: %s', flavor)
        return self.dict[flavor]