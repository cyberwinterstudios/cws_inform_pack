import requests
import pendulum
import boto3
from urllib.parse import urljoin
from zipfile import ZipFile
from io import BytesIO, StringIO
from csv import DictReader

from st2common.runners.base_action import Action


def extract_zip(zip_file):
    input_zip = ZipFile(zip_file)
    return [{"filename": name, "file": input_zip.read(name).decode("utf-8-sig")} for name in input_zip.namelist()]

field_map = {
    "AirmanId": "u_id",
    "MedicalComplete": "u_medical_completed_on",
    "MedicalDue": "u_medical_due_on",
    "MedicalScheduled": "u_medical_scheduled_on",
    "CbrneComplete": "u_cbrne_completed_on",
    "CbrneDue": "u_cbrne_due_dn",
    "CbrneScheduled": "u_cbrne_scheduled_on",
    "XYZ": "u_id",
    "ABC123": "u_afsc_completed_on",
    "DEF456": "u_afsc_due_on",
    "ABC456": "u_afsc_scheduled_on",
    "GHI789": "u_fitness_completed_on",
    "JKL012": "u_fitness_due_on",
    "GHI012": "u_fitness_scheduled_on",
    "012ABC": "u_catm_completed_on",
    "345DEF": "u_catm_due_on",
    "012DEF": "u_catm_scheduled On",
    "Wing": "u_wing",
    "Flight Group": "u_flight_group",
    "Squadron": "u_squadron",
    "Name": "u_name"
}


class UpdateAirmen(Action):

    def __init__(self, *args, **kwargs):
        super(UpdateAirmen, self).__init__(*args, **kwargs)
        self.snow_url = self.config['snow_url']
        self.snow_username = self.config['snow_username']
        self.snow_password = self.config['snow_password']
        self.s = requests.session()
        self.base_url = urljoin(self.snow_url, "/api/now/")

        self.s.auth = (self.snow_username, self.snow_password)
        
        self.client = boto3.Session(aws_access_key_id=self.config['aws_access_key_id'],
                                    aws_secret_access_key=self.config['aws_secret_access_key'],
                                    region_name=self.config['region'])
        self.s3_client = self.client.client('s3')

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

    def run(self):

        try:
            last_check_time = pendulum.parse(self.action_service.get_value(name="s3_check_time"))
        except:
            last_check_time = pendulum.now().subtract(minutes=30)
        
        files = self.s3_client.list_objects(Bucket="readiness-files")

        for f in files['Contents']:
            if f['LastModified'] > last_check_time:
                file_response = self.s3_client.get_object(Bucket="readiness-files", Key=f["Key"])
                file_contents = BytesIO(file_response['Body'].read())
                self.action_service.set_value(name="s3_check_time", value=f['LastModified'].isoformat())

                zipped_files = extract_zip(file_contents)
                for zf in zipped_files:
                    csv = DictReader(StringIO(zf['file']))
                    for row in csv:
                        airman_id = row.get("AirmanId", row.get("XYZ"))
                        if not airman_id:
                            raise ValueError(f"No Airman Id found in row of {zf['filename']}")

                        params = {
                            "sysparm_query": f"u_airmen_id={airman_id}"
                        }
                        airman_records = self.request('get', 'table/u_readiness', params=params).json()['result']
                        if airman_records:
                            airman_record = airman_records[0]
                            for key in row:
                                if not field_map.get(key):
                                    continue
                                value = row[key]
                                airman_record[field_map[key]] = value
                            airman_record = self.request('patch', f'table/u_readiness/{airman_record["sys_id"]}',
                                                         json=airman_record).json()['result']
                        else:
                            data = dict()
                            for key in row:
                                if not field_map.get(key):
                                    continue
                                value = row[key]
                                data[field_map[key]] = value
                                airman_record = self.request('post', 'table/u_readiness', json=data).json()['result']
