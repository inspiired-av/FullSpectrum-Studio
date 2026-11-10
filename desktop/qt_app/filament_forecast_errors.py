"""User-facing, single-cause summaries for palette configuration failures.

Do not hide unrelated optimizer failures or convert failure to success.
"""
from __future__ import annotations

import re

_TOO_FEW = re.compile(r'Filament source contains fewer than\s+(\d+)\s+distinct colors',re.I)
_QUALITY_PREFIX = re.compile(r'^\s*\d{1,3}:\s*')


def describe_forecast_failure(error, physical_slots='auto', available_colors=None):
    message = str(error).strip()
    if not message:
        return 'Unknown forecasting error.'
    shortage = _TOO_FEW.findall(message)
    if shortage and len(set(shortage)) == 1:
        required = int(shortage[0])
        count = (int(available_colors) if isinstance(available_colors,int) and
                 not isinstance(available_colors,bool) and available_colors >= 0 else None)
        details = (f'{count} distinct enabled colors' if count is not None
                   else 'fewer available distinct colors')
        if str(physical_slots).strip() == str(required):
            return (f'Physical slots is set to {required} in Plan → Advanced Settings, '
                    f'but the selected source has {details}. Set Physical slots to Auto '
                    f'or a supported lower count, or enable more distinct filaments.')
        if str(physical_slots).lower().strip() == 'auto':
            return (f'Automatic slot planning requested {required} physical colors, '
                    f'but the selected source has {details}. Verify enabled colors and '
                    'Physical slots in Plan → Advanced Settings.')
    if message.startswith('Smart quality planning failed:'):
        attempts = message.partition(':')[2].split(';')
        distinct = []
        for attempt in attempts:
            reason = _QUALITY_PREFIX.sub('',attempt).strip()
            if reason and reason not in distinct:
                distinct.append(reason)
        if distinct:
            if len(distinct)==1:
                return 'Smart quality planning failed: '+distinct[0]
            return ('Smart quality planning failed: ' + '; '.join(distinct[:2]) +
                    (' (additional attempts omitted)' if len(distinct)>2 else ''))
    return message
