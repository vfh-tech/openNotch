import logging
from datetime import datetime, timedelta, timezone

import gi

gi.require_version('ECal', '2.0')
gi.require_version('EDataServer', '1.2')
gi.require_version('ICalGLib', '3.0')
from gi.repository import ECal, EDataServer, GLib, ICalGLib

from agenda import AgendaEntry, Kind

CONNECT_TIMEOUT = 5
EVENT = ICalGLib.ComponentKind.VEVENT_COMPONENT
TASK = ICalGLib.ComponentKind.VTODO_COMPONENT
SUMMARY = ICalGLib.PropertyKind.SUMMARY_PROPERTY
STATUS = ICalGLib.PropertyKind.STATUS_PROPERTY
DTSTART = ICalGLib.PropertyKind.DTSTART_PROPERTY
DUE = ICalGLib.PropertyKind.DUE_PROPERTY


def _text(component, kind):
    prop = component.get_first_property(kind)
    return prop.get_value_as_string() if prop is not None else ''


def _time(component, kind):
    prop = component.get_first_property(kind)
    if prop is None:
        return None
    value = prop.get_datetime_with_component(component)
    if value is None:
        return None
    moment = datetime(value.get_year(), value.get_month(), value.get_day(),
                      value.get_hour(), value.get_minute())
    return moment, bool(value.is_date())


def entry_from(component, source):
    kind = Kind.EVENT if component.isa() == EVENT else Kind.TASK
    title = _text(component, SUMMARY) or '(tanpa judul)'
    if kind is Kind.TASK:
        due = _time(component, DUE)
        if due is None:
            return None
        done = _text(component, STATUS).upper() in ('COMPLETED', 'CANCELLED')
        return AgendaEntry(title, kind, due[0], all_day=due[1], done=done, source=source)
    start = _time(component, DTSTART)
    if start is None:
        return None
    return AgendaEntry(title, kind, start[0], all_day=start[1], source=source)


def event_sexp(now):
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    fmt = '%Y%m%dT%H%M%SZ'
    stamp = lambda moment: moment.astimezone(timezone.utc).strftime(fmt)
    return (f'(occur-in-time-range? (make-time "{stamp(start)}")'
            f' (make-time "{stamp(end)}"))')


def client_entries(source, now):
    calendar = source.get_extension('Calendar')
    tasks = source.get_extension('TaskList')
    extension = calendar or tasks
    if extension is None or not extension.get_selected():
        return []
    is_event = calendar is not None
    source_type = ECal.ClientSourceType.EVENTS if is_event else ECal.ClientSourceType.TASKS
    client = ECal.Client.connect_sync(source, source_type, CONNECT_TIMEOUT, None)
    if client is None:
        return []
    wanted = EVENT if is_event else TASK
    sexp = event_sexp(now) if is_event else '(contains? "SUMMARY" "")'
    ok, components = client.get_object_list_sync(sexp, None)
    if not ok or components is None:
        return []
    entries = []
    for component in components:
        if component.isa() != wanted:
            continue
        entry = entry_from(component, source.get_uid())
        if entry is not None:
            entries.append(entry)
    return entries


def load(now=None):
    now = now or datetime.now()
    registry = EDataServer.SourceRegistry.new_sync(None)
    entries = []
    for source in registry.list_sources(None):
        if not (source.get_extension('Calendar') or source.get_extension('TaskList')):
            continue
        try:
            entries.extend(client_entries(source, now))
        except GLib.Error as exc:
            logging.debug('Agenda source %s unavailable: %s', source.get_uid(), exc)
    return entries