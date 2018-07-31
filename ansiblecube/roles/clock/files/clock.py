#!/usr/bin/env python
# -*- coding: utf-8 -*-

''' hardware clock management UI

    - set HW clock using system time
    - set HW clock manually
    - set system time using HW clock '''

# https://linux.die.net/man/8/hwclock
# https://afterthoughtsoftware.com/products/rasclock
# https://www.cyberciti.biz/faq/howto-set-date-time-from-linux-command-prompt/

import re
import urllib
import subprocess

header = u"""<html><head><meta charset="utf-8"><style type="text/css">th { text-align: left; }</style></head>"""

body = u"""<body>
<h1><a href="/">Pi Time</a></h1>
{output}
<table>
<tr><th>System date</th><td>{system_time}</td></tr>
<tr><th>Hardware date</th><td>{hardware_time}</td></tr>
</table>
<h1>Configure Hardware Clock (online)</h1>
<p>Use this option if the hardware clock is far behind the system one or unavailable.</p>
<p>This is what you would do to <strong>configure a newly plugged hardware clock</strong> using a <strong>connected Pi</strong>.</p>
<form action="/sys2hw" method="GET">
<input type="submit" value="Copy System Time into Hardware Clock" />
</form>

<h1>Configure Hardware Clock (offline)</h1>
<p>Use this option if neither the Hardware Clock nor the System clock is right.</p>
<p>This is what you would do to <strong>configure a newly plugged hardware clock</strong> using a <strong>not-connected Pi</strong>.</p>
<form action="/manual2hw" method="GET">
<input name="datetime" type="text" pattern="[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]" required="required" placeholder="2017-12-01 20:30" />
<input type="submit" value="Save this time into Hardware Clock" />
</form>
</body>

<h1>Update System Clock</h1>
<p>Use this option if the system clock is far behind the hardware one.</p>
<p>This step is not required as this is done upon system startup but can help you check the process.</p>
<form action="/hw2sys" method="GET">
<input type="submit" value="Update System Time with Hardware Clock one" />
</form>
"""

footer = u"</html>"

date_bin = '/bin/date'
hwclock_bin = '/sbin/hwclock'
tdctl_bin = '/usr/bin/timedatectl'


def get_output(command):
    try:
        return subprocess.check_output(['sudo'] + command).strip()
    except Exception as exp:
        return "ERROR: {}".format(exp)


def application(env, start_response):
    output = ""

    if env['REQUEST_URI'] == '/sys2hw':
        # write system datetime into hardware clock
        output = get_output([hwclock_bin, '-w'])

    if env['REQUEST_URI'] == '/hw2sys':
        # set system datetime using hardware clock
        output = get_output([hwclock_bin, '-s'])

    if env['REQUEST_URI'].startswith('/manual2hw'):
        # write a manual datetime into hardware clock
        try:
            dt = urllib.unquote_plus(env['QUERY_STRING']) \
                .split('datetime=')[1]
            # disable ntp otherwise we can't set manual date
            get_output([tdctl_bin, 'set-ntp', 'no'])
            # set manual date
            output = get_output([tdctl_bin, 'set-time', dt])
            # re-enable ntp. if online, will overwrite our manual datetime
            get_output([tdctl_bin, 'set-ntp', 'yes'])
        except Exception as exp:
            output = "ERROR: {}".format(exp)

    context = {
        'output': '<p style="color: blue; font-weight: bold;">{}</p>'
        .format(output),
        'system_time': get_output(
            [date_bin, '+"%Y-%m-%d %H:%M:%S.000000%z"'])[1:-1],
        'hardware_time': get_output([hwclock_bin, '-r']),
    }

    start_response('200 OK', [('Content-Type', 'text/html')])
    page = header + body.format(**context) + footer
    return [page.encode('utf-8')]
