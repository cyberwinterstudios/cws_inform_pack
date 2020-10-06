import requests
import pendulum
from urllib.parse import urljoin

from st2common.runners.base_action import Action


class UpdateReadiness(Action):

    def __init__(self, *args, **kwargs):
        super(UpdateReadiness, self).__init__(*args, **kwargs)
        self.snow_url = self.config['snow_url']
        self.snow_username = self.config['snow_username']
        self.snow_password = self.config['snow_password']
        self.s = requests.session()
        self.base_url = urljoin(self.snow_url, "/api/now/")

        self.s.auth = (self.snow_username, self.snow_password)

    def request(self, method, endpoint, **kwargs):
        while(endpoint.startswith("/")):
            endpoint.lstrip("/")

        response = self.s.request(method=method, url=urljoin(self.base_url, endpoint), **kwargs)
        response.raise_for_status()
        return response

    def convert_to_ints(self, d):
        for key in d:
            try:
                d[key] = int(d[key])
            except:
                pass
        return d

    def run(self, sys_id):

        airman_record = self.request('get', f'table/u_readiness/{sys_id}').json()["result"]
        airman_record = self.convert_to_ints(airman_record)

        now = pendulum.now()

        fields = ['u_fitness', 'u_afsc', 'u_catm', 'u_medical', 'u_cbrne']
        for field in fields:
            due_on = f'{field}_due_on'
            completed_on = f'{field}_completed_on'
            if not airman_record[completed_on]:
                percentage = 0
            else:
                completed_date = pendulum.parse(airman_record[completed_on])
                due_date = pendulum.parse(airman_record[due_on])

                if completed_date < due_date.subtract(days=30) or completed_date > due_date:
                    percentage = 100
                else:
                    if due_date > now:
                        days_to_expire = due_date.diff(now).in_days()
                        percentage = int(round((days_to_expire/30) * 100))
                    else:
                        percentage = 0
            if percentage < 0:
                percentage = 0
            airman_record[field] = percentage

        readiness = (sum([airman_record[v] for v in fields])) / len(fields)
        airman_record['u_readiness'] = readiness
        airman_record = self.request('patch', f'table/u_readiness/{sys_id}', json=airman_record).json()

        return airman_record
