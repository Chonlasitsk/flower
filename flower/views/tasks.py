import copy
import logging
from functools import total_ordering
import re
import json

from tornado import web

from ..utils.tasks import as_dict, get_task_by_id, iter_tasks
from ..utils.task_state import TaskStatus
from ..views import BaseHandler

logger = logging.getLogger(__name__)

class TaskView(BaseHandler):
    @web.authenticated
    def get(self, task_id):
        task = get_task_by_id(self.application.events, task_id)
        if task is None:
            raise web.HTTPError(404, f"Unknown task '{task_id}'")
        task = self.format_task(task)
        task_dict = as_dict(task)
        logger.debug(f"task_dict: {task_dict}")
        # task_from_redis = self.application.redis_client.get_task_by_id(task_id)
        # task_from_redis_dict = json.loads(task_from_redis)
        self.render("task.html", task=task)


@total_ordering
class Comparable:
    """
    Compare two objects, one or more of which may be None.  If one of the
    values is None, the other will be deemed greater.
    """

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return self.value == other.value

    def __lt__(self, other):
        try:
            return self.value < other.value
        except TypeError:
            return self.value is None


class TasksDataTable(BaseHandler):
    @web.authenticated
    def get(self):
        app = self.application
        draw = self.get_argument('draw', type=int)
        start = self.get_argument('start', type=int)
        length = self.get_argument('length', type=int)
        search = self.get_argument('search[value]', type=str)

        column = self.get_argument('order[0][column]', type=int)
        sort_by = self.get_argument(f'columns[{column}][data]', type=str)
        sort_order = self.get_argument('order[0][dir]', type=str) == 'desc'

        filter_state = self.get_argument('columns[2][search][value]', type=str)

        def key(item):
            return Comparable(getattr(item[1], sort_by))

        self.maybe_normalize_for_sort(app.events.state.tasks_by_timestamp(), sort_by)

        sorted_tasks = sorted(
            iter_tasks(app.events, search=search),
            key=key,
            reverse=sort_order
        )
        logger.debug(f"Number of sorted tasks: {len(sorted_tasks)}")

        # NOTE filter tasks by state
        if filter_state:
            logger.debug(f"Filtering tasks by state: {filter_state}")
            pattern = re.compile(filter_state)
            sorted_tasks = [task for task in sorted_tasks if pattern.match(task[1].state)]
            logger.debug(f"Number of filtered tasks by state: {len(sorted_tasks)}")

        sorted_tasks_paginated = sorted_tasks[start:start + length]

        # for task in sorted_tasks_paginated:
        #     task_dict = as_dict(self.format_task(task)[1])
        #     if task_dict.get('worker'):
        #         task_dict['worker'] = task_dict['worker'].hostname
        #     task_dict['service'] = 'test-service'
        #     task_dict['upstream'] = 'test-upstream'
        #     filtered_tasks.append(task_dict)

        # ✅ TODO: handle case when task still in celery queue or expired or removed from redis (PENDING STATE)
        # TODO: handle case when task is expired
        task_ids = [task[0] for task in sorted_tasks_paginated]
        task_ttls = self.application.redis_client.get_ttls_by_id(task_ids)
        tasks_from_redis = self.application.redis_client.get_tasks_by_id(task_ids)
        tasks_from_redis_dict = [None] * len(sorted_tasks_paginated)

        for idx, task in enumerate(tasks_from_redis):
            if task:
                tasks_from_redis_dict[idx] = json.loads(task)
            else:
                tasks_from_redis_dict[idx] = None

        logger.debug(f"Number of task_ttls: {len(task_ttls)}")
        logger.debug(f"Number of tasks_from_redis_dict: {len(tasks_from_redis_dict)}")
        logger.debug(f"Number of sorted_tasks_paginated: {len(sorted_tasks_paginated)}")
        filtered_tasks = [None] * len(sorted_tasks_paginated)
        for idx, (task, task_from_redis, task_ttl) in enumerate(zip(sorted_tasks_paginated, tasks_from_redis_dict, task_ttls)):
            task_dict = as_dict(self.format_task(task)[1])
            if task_dict.get('worker'):
                task_dict['worker'] = task_dict['worker'].hostname

            if task_dict['state'] == TaskStatus.STARTED:
                if task_from_redis:
                    if task_from_redis['status'] == TaskStatus.PROCESSING:
                        task_dict['service'] = task_from_redis['result']['service']
                        task_dict['upstream'] = task_from_redis['result']['target'] if task_from_redis['result']['target'] else task_from_redis['result']['upstream_url']
                        task_dict['expired'] = "No" if task_ttl > 0 else "Yes"
                    else:
                        task_dict['service'] = None
                        task_dict['upstream'] = None
                        task_dict['expired'] = "No" if task_ttl > 0 else "Yes"
                else:
                    task_dict['service'] = None
                    task_dict['upstream'] = None
                    task_dict['expired'] = "No" if task_ttl > 0 else "Yes"
            elif task_dict['state'] == TaskStatus.SUCCESS:
                if task_from_redis:
                    task_dict['service'] = task_from_redis['result']['service']
                    task_dict['upstream'] = task_from_redis['result']['target'] if task_from_redis['result']['target'] else task_from_redis['result']['upstream_url']
                    task_dict['expired'] = "No" if task_ttl > 0 else "Yes"
                else:
                    task_dict['service'] = None
                    task_dict['upstream'] = None
                    task_dict['expired'] = "No" if task_ttl > 0 else "Yes"
            elif task_dict['state'] == TaskStatus.FAILURE:
                if task_from_redis:
                    task_dict['service'] = task_from_redis['result']['exc_message'][0]['exc_data']['service']
                    task_dict['upstream'] = task_from_redis['result']['exc_message'][0]['exc_data']['target'] if task_from_redis['result']['exc_message'][0]['exc_data']['target'] else task_from_redis['result']['exc_message'][0]['exc_data']['upstream_url']
                    task_dict['expired'] = "No" if task_ttl > 0 else "Yes"
                else:
                    task_dict['service'] = None
                    task_dict['upstream'] = None
                    task_dict['expired'] = "No" if task_ttl > 0 else "Yes"
            elif task_dict['state'] == TaskStatus.PENDING:
                task_dict['service'] = None
                task_dict['upstream'] = None
                task_dict['expired'] = "No"

            filtered_tasks[idx] = task_dict


        self.write(dict(draw=draw, data=filtered_tasks,
                        recordsTotal=len(sorted_tasks),
                        recordsFiltered=len(sorted_tasks)))

    @classmethod
    def maybe_normalize_for_sort(cls, tasks, sort_by):
        sort_keys = {'name': str, 'state': str, 'received': float, 'started': float, 'runtime': float}
        if sort_by in sort_keys:
            for _, task in tasks:
                attr_value = getattr(task, sort_by, None)
                if attr_value:
                    try:
                        setattr(task, sort_by, sort_keys[sort_by](attr_value))
                    except TypeError:
                        pass

    @web.authenticated
    def post(self):
        return self.get()

    def format_task(self, task):
        uuid, args = task
        custom_format_task = self.application.options.format_task
        if custom_format_task:
            try:
                args = custom_format_task(copy.copy(args))
            except Exception:
                logger.exception("Failed to format '%s' task", uuid)
        return uuid, args


class TasksView(BaseHandler):
    @web.authenticated
    def get(self):
        app = self.application
        capp = self.application.capp

        time = 'natural-time' if app.options.natural_time else 'time'
        if capp.conf.timezone:
            time += '-' + str(capp.conf.timezone)

        show_columns = app.options.tasks_columns + ',service' + ',upstream' + ',expired'

        self.render(
            "tasks.html",
            tasks=[],
            columns=show_columns, #NOTE define which columns to display in UI ex. 'all' -> show all columns
            time=time,
        )
