import requests
import pendulum
from urllib.parse import urljoin

from st2common.runners.base_action import Action


class UpdateInventory(Action):

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

    def fill_in_inventory(self, oldest_record, start_date, end_date, planes, missiles, airmen):

        mission_started = True

        oldest_planes = oldest_record['u_planes']
        oldest_missiles = oldest_record['u_missiles']
        oldest_airmen = oldest_record['u_airmen']
        oldest_total_planes = oldest_record['u_total_planes']
        oldest_total_missiles = oldest_record['u_total_missiles']
        oldest_total_airmen = oldest_record['u_total_airmen']

        p_start_date = pendulum.parse(start_date)
        p_end_date = pendulum.parse(end_date)
        inventory_date = pendulum.parse(oldest_record['u_date']).add(days=1)
        while inventory_date < p_start_date:
            mission_started = False
            data = {
                "u_date": inventory_date.to_date_string(),
                "u_missiles": oldest_missiles,
                "u_planes": oldest_planes,
                "u_airmen": oldest_airmen,
                "u_total_missiles": oldest_total_missiles,
                "u_total_planes": oldest_total_planes,
                "u_total_airmen": oldest_total_airmen
            }
            self.request("post", 'table/u_daily_inventory', json=data).json()
            inventory_date = inventory_date.add(days=1)

        if not mission_started:
            mission_planes = oldest_planes - planes
            mission_missiles = oldest_missiles - missiles
            mission_airmen = oldest_airmen - airmen
        else:
            mission_planes = oldest_planes
            mission_missiles = oldest_missiles
            mission_airmen = oldest_airmen

        while inventory_date < p_end_date:
            data = {
                "u_date": inventory_date.to_date_string(),
                "u_missiles": mission_missiles,
                "u_planes": mission_planes,
                "u_airmen": mission_airmen,
                "u_total_missiles": oldest_total_missiles,
                "u_total_planes": oldest_total_planes,
                "u_total_airmen": oldest_total_airmen
            }
            inventory_date = inventory_date.add(days=1)

        if mission_started:
            oldest_planes += planes
            oldest_airmen += airmen

        data = {
            "u_date": inventory_date.to_date_string(),
            "u_missiles": mission_missiles,
            "u_planes": oldest_planes,
            "u_airmen": oldest_airmen,
            "u_total_missiles": oldest_total_missiles,
            "u_total_planes": oldest_total_planes,
            "u_total_airmen": oldest_total_airmen
        }
        latest_record = self.request("post", 'table/u_daily_inventory', json=data).json()

        return latest_record

    def run(self, sys_id):
        snow_url = self.config['snow_url']
        snow_username = self.config['snow_username']
        snow_password = self.config['snow_password']

        self.s = requests.session()
        self.base_url = urljoin(snow_url, "/api/now/")
        self.s.auth = (snow_username, snow_password)

        request_record = self.request('get', f'table/u_inventory_request/{sys_id}').json()["result"]
        request_record = self.convert_to_ints(request_record)

        start_date = request_record['u_start_date']
        end_date = request_record['u_end_date']
        p_end_date = pendulum.parse(end_date)

        params = {
            "sysparm_query": f"u_date>=javascript:gs.dateGenerate('{start_date}', 'end')^ORDERBYDESCu_date",
        }

        inventory_records = self.request('get', f'table/u_daily_inventory', params=params).json()["result"]

        oldest_record_date = None
        for record in inventory_records:
            date = pendulum.parse(record['u_date'])
            record['u_missiles'] -= request_record['u_missiles']
            record['u_total_missiles'] -= request_record['u_missiles']
            if date <= p_end_date:
                record['u_planes'] -= request_record['u_planes']
                record['u_airmen'] -= request_record['u_airmen']
            self.request('patch', f'table/u_daily_inventory/{record["sys_id"]}', json=record)
            oldest_record_date = date

        if not oldest_record_date or oldest_record_date <= p_end_date:
            oldest_params = {
                "sysparm_limit": 1,
                "sysparm_query": "ORDERBYDESCu_date"
            }
            oldest_records = self.request('get', f'table/u_daily_inventory', params=oldest_params).json()["result"]
            oldest_record = self.convert_to_ints(oldest_records[0])
            oldest_record = self.fill_in_inventory(oldest_record, start_date, end_date, request_record['u_planes'],
                                                   request_record['u_missiles'], request_record['u_airmen'])



        return oldest_record
