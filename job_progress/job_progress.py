from __future__ import absolute_import
import uuid

from job_progress import states


def _generate_id():
    """Return job unique id."""
    return str(uuid.uuid4())


class JobProgress(object):

    backend = None
    session = None

    def __init__(self, data, amount, id_=None, state=None,
                 previous_state=None, loading=False):
        self.data = data
        self.amount = amount
        state = state or states.PENDING
        self._previous_state = previous_state or states.PENDING
        self.id = id_ or _generate_id()

        if not loading:
            # Store in the back-end
            self.backend.initialize_job(self.id, self.data, state,
                                        self.amount)
            self.session.add(self.id, self)

    def __repr__(self):
        return "<JobProgress '%s'>" % self.id

    @classmethod
    def from_backend(cls, data, amount, id_, state, previous_state):
        """Load from backend."""

        self = cls(data, amount, id_, state, previous_state, loading=True)
        return self

    @property
    def backend(self):
        """Return backend instance."""
        return self.backend_factory()

    @property
    def is_ready(self):
        """Return True if is ready."""
        return self.state in states.READY_STATES

    @property
    def state(self):
        """Return state."""
        return self.backend.get_state(self.id)

    @state.setter  # noqa
    def state(self, state):
        """Set the state."""
        self.backend.set_state(self.id, state, self._previous_state)
        self._previous_state = state

    @property
    def is_staled(self):
        """Return True if staled."""
        return self.state == states.STARTED and self.backend.is_staled(self.id)

    def add_one_progress_state(self, state, item_id=None):
        """Add one unit status."""
        return self.backend.add_one_progress_state(self.id, state, item_id)

    def add_one_failure(self, item_id=None):
        """Add one failure state.

        :param item_id: Details with this progress. If it is None, then no
                        details will be added for this progress.
        """
        self.add_one_progress_state(states.FAILURE, item_id)

    def add_one_success(self, item_id=None):
        """Add one success state.

        :param item_id: Details with this progress. If it is None, then no
                        details will be added for this progress.
        """
        self.add_one_progress_state(states.SUCCESS, item_id)

    def track(self, is_success, item_id=None):
        """Check if an object is_success or not. If failed, put it in
        failure detailed progress and increase failure counter. If
        not, put it in success detailed progress and increase success
        counter.

        If no value provided, only modify the counter.
        """
        if is_success:
            self.add_one_success(item_id)
        else:
            self.add_one_failure(item_id)

    def get_detailed_progress(self, *states_):
        """Get all detailed progress for the job

        Only states that has details added will be returned.
        :rtype: dict

        E.g.::

            {
            "success": set([1, 2, 3]),
            "failure": set([4, 5]),
            }
        """
        if not states_:
            states_ = self.backend.get_all_detailed_progress_states(self.id)

        result = {}
        for state in states_:
            result[state] = self.backend.get_detailed_progress_by_state(
                self.id, state
            )

        return result

    def get_progress(self):
        """Return the progress.

        :rtype: dict

        E.g.::

            {
            "success": 12,
            "failure": 14,
            "pending": 32,
            }
        """
        progress = self.backend.get_progress(self.id)
        progress = {k: int(v) for k, v in progress.items()}

        pending = 0
        if self.amount:
            # There can be a race condition before we have saved amount.
            pending = int(self.amount) - sum(progress.values())

        if pending:
            progress[states.PENDING] = pending

        return progress

    def to_dict(self, include_details=False):
        """Return dict representation of the object.

        If `include_details` is True, the result will include detailed
        progress info.
        """
        returned = {
            "id": self.id,
            "data": self.data,
            "amount": self.amount,
            "progress": self.get_progress(),
            "is_ready": self.is_ready,
            "state": self.state,
        }
        if include_details:
            returned['detailed_progress'] = self.get_detailed_progress()
        return returned

    def delete(self):
        """Delete the job."""
        self.backend.delete_job(self.id, self.state)

    @classmethod
    def query(cls, **filters):
        """Query the backend.

        :param filters: filters.

        Currently supported filters are:

        - ``is_ready``
        - ``state``

        This method should be considered alpha.
        """

        ids = cls.backend.get_ids(**filters)
        return [cls.session.get(id_) for id_ in ids]
