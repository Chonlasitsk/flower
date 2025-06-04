import copy
import logging
from functools import total_ordering
import re

from tornado import web

from ..utils.tasks import as_dict, get_task_by_id, iter_tasks
from ..views import BaseHandler

logger = logging.getLogger(__name__)


class TaskView(BaseHandler):
    @web.authenticated
    def get(self, task_id):
        task = get_task_by_id(self.application.events, task_id)

        if task is None:
            raise web.HTTPError(404, f"Unknown task '{task_id}'")
        task = self.format_task(task)

        # logger.info(f"Get all task attributes: {task.__dict__}")
        # logger.info(f"Task state: {task.state}")
        # logger.info(f"Task result: {task.result}")
        # logger.info(f"Task args: {task.args}")
        # logger.info(f"Task kwargs: {task.kwargs}")
        # logger.info(f"Task traceback: {task.traceback}")
        # logger.info(f"Task worker: {task.worker}")
        # logger.info(f"Task name: {task.name}")
        # logger.info(f"Task exception: {task.exception}")
        # logger.info(f"Task exception (type): {type(task.exception)}")
        # logger.info(f"Task fields: {task._fields}")
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
        logger.info(f"Number of sorted tasks: {len(sorted_tasks)}")

        #NOTE filter tasks by state
        if filter_state:
            logger.info(f"Filtering tasks by state: {filter_state}")
            pattern = re.compile(filter_state)
            sorted_tasks = [task for task in sorted_tasks if pattern.match(task[1].state)]
            logger.info(f"Number of filtered tasks by state: {len(sorted_tasks)}")

        filtered_tasks = []
        for task in sorted_tasks[start:start + length]:
            logger.info(f"Task: {task}")
            task_dict = as_dict(self.format_task(task)[1])
            if task_dict.get('worker'):
                task_dict['worker'] = task_dict['worker'].hostname
            task_dict['service'] = "asr_service"
            task_dict['upstream'] = "asr_upstream"
            filtered_tasks.append(task_dict)
        logger.info(f"Filtered task: {filtered_tasks[0]}")

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

        logger.info(f"tasks_columns: {app.options.tasks_columns}")
        logger.info(f"type of tasks_columns: {type(app.options.tasks_columns)}")
        show_columns = app.options.tasks_columns + ',service' + ',upstream'

        self.render(
            "tasks.html",
            tasks=[],
            columns=show_columns, #NOTE define which columns to display in UI ex. 'all' -> show all columns
            time=time,
        )
