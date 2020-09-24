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

    def fill_in_inventory(self, oldest_record, end_date, planes, missiles, airmen):
        oldest_planes = oldest_record['u_planes']
        oldest_missiles = oldest_record['u_missiles']
        oldest_airmen = oldest_record['u_airmen']
        oldest_total_planes = oldest_record['u_total_planes']
        oldest_total_missiles = oldest_record['u_total_missiles']
        oldest_total_airmen = oldest_record['u_total_airmen']

        p_end_date = pendulum.parse(end_date)
        inventory_date = pendulum.parse(oldest_record['u_date']).add(days=1)
        while inventory_date < p_end_date:
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

        new_planes = oldest_planes + planes
        new_missiles = oldest_missiles + missiles
        new_airmen = oldest_airmen + airmen
        new_total_planes = oldest_total_planes + planes
        new_total_missiles = oldest_total_missiles + missiles
        new_total_airmen = oldest_total_airmen + airmen

        latest_data = {
            "u_date": inventory_date.to_date_string(),
            "u_missiles": new_missiles,
            "u_planes": new_planes,
            "u_airmen": new_airmen,
            "u_total_missiles": new_total_missiles,
            "u_total_planes": new_total_planes,
            "u_total_airmen": new_total_airmen
        }
        latest_record = self.request("post", 'table/u_daily_inventory', json=latest_data).json()

        return latest_record

    def run(self, sys_id):
        snow_url = self.config['update_inventory']['snow_url']
        snow_username = self.config['update_inventory']['snow_username']
        snow_password = self.config['update_inventory']['snow_password']

        self.s = requests.session()
        self.base_url = urljoin(snow_url, "/api/now/")
        self.s.auth = (snow_username, snow_password)

        adjustment_record = self.request('get', f'table/u_inventory_adjustment/{sys_id}').json()["result"]
        adjustment_record = self.convert_to_ints(adjustment_record)

        date = adjustment_record['u_date_of_adjustment']  # pendulum.parse(adjustment_record['u_date_of_adjustment'])

        params = {
            "sysparm_query": f"u_date>=javascript:gs.dateGenerate('{date}', 'end')^ORDERBYDESCu_date",
        }

        inventory_records = self.request('get', f'table/u_daily_inventory', params=params).json()["result"]

        if not inventory_records:
            oldest_params = {
                "sysparm_limit": 1,
                "sysparm_query": "ORDERBYDESCu_date"
            }
            oldest_records = self.request('get', f'table/u_daily_inventory', params=oldest_params).json()["result"]

            if not oldest_records:
                data = {
                    "u_date": adjustment_record["u_date_of_adjustment"],
                    "u_missiles": adjustment_record["u_missiles"],
                    "u_planes": adjustment_record["u_planes"],
                    "u_airmen": adjustment_record["u_airmen"],
                    "u_total_missiles": adjustment_record["u_missiles"],
                    "u_total_planes": adjustment_record["u_planes"],
                    "u_total_airmen": adjustment_record["u_airmen"]
                }
                new_record = self.request("post", 'table/u_daily_inventory', json=data).json()

            else:
                oldest_record = self.convert_to_ints(oldest_records[0])
                latest_record = self.fill_in_inventory(oldest_record,
                                                       adjustment_record['u_date_of_adjustment'],
                                                       adjustment_record['u_planes'],
                                                       adjustment_record['u_missiles'],
                                                       adjustment_record["u_airmen"])

        else:
            fields = ['missiles', 'airmen', 'planes']
            for record in inventory_records:
                record = self.convert_to_ints(record)
                for f in fields:
                    field = f'u_{f}'
                    total_field = f'u_total_{f}'
                    if adjustment_record[field]:
                        record[field] += adjustment_record[field]
                        record[total_field] += adjustment_record[field]
                self.request("patch", f"table/u_daily_inventory/{record['sys_id']}", json=record)

        return adjustment_record
