import sys
import time
from collections import defaultdict
from urlparse import urljoin

import requests
from bokeh.plotting import figure, save, output_file

treeherder_base = "http://treeherder.mozilla.org"

now = time.time()

def load_results_set_data(repository, revision):
    url = urljoin(treeherder_base,
                  "/api/project/%s/resultset/?count=1&full=true&revision=%s" %
                  (repository, revision))
    resp = requests.get(url)
    return resp.json()

def results_set_properties(data):
    return data["results"][0]["id"], data["results"][0]["push_timestamp"]

def load_jobs_data(repository, result_set_id):
    url = urljoin(treeherder_base,
                  "/api/project/%s/jobs/?count=2000&result_set_id=%i&return_type=list" %
                  (repository, result_set_id))
    resp = requests.get(url)
    return resp.json()

def data_indicies(data):
    fields = {"id", "submit_timestamp", "start_timestamp", "end_timestamp", "ref_data_name",
              "tier", "platform", "job_coalesced_to_guid"}
    indicies = {}
    for i, value in enumerate(data["job_property_names"]):
        if value in fields:
            indicies[i] = value

    assert len(indicies) == len(fields)
    return indicies


def extract_fields(data):
    indicies = data_indicies(data)
    rv = []
    for job in data["results"]:
        job_data = {key:job[idx] for idx,key in indicies.iteritems()}
        rv.append(job_data)

    return rv

def filter_tier(data):
    return [item for item in data if item["tier"] == 1]

def filter_coalesced(data):
    return [item for item in data if item["job_coalesced_to_guid"] is None]

def compute_offsets(push_timestamp, data):
    def offset(timestamp):
        if timestamp == 0:
            print job["ref_data_name"], job
            return (now - push_timestamp) / 60

        return (timestamp - push_timestamp) / 60

    for job in data:
        job["offsets"] = {"pending_start": offset(job["submit_timestamp"]),
                          "pending_end": offset(job["start_timestamp"])}
        if job["start_timestamp"]:
            job["offsets"]["running_start"] = offset(job["start_timestamp"])
            job["offsets"]["running_end"] = offset(job["end_timestamp"])

    return data

def group_by_type(job_data):
    by_type = defaultdict(list)
    for item in job_data:
        by_type[item["ref_data_name"]].append(item)

    for key, items in by_type.iteritems():
        items.sort(key=lambda x: x["submit_timestamp"])

    return by_type

def sort_by_id(by_type):
    rv = []
    for item in sorted(by_type.items(), key=lambda x: x[1][0]["id"]):
        rv.append(item)
    return rv

def pipeline(data, *args):
    in_value = data
    for item in args:
        in_value = item(in_value)
    return in_value

def colours(job):
    palette = {"android-2-3-armv7-api9": "#44FF00",
               "android-4-0-armv7-api11": "#44CC00",
               "android-4-2-x86": "#44AA00",
               "android-4-3-armv7-api11": "#448800",
               "b2g-device-image": "#00FF44",
               "b2g-emu-ics": "#00CC44",
               "b2g-linux64": "#00AA44",
               "linux32": "#00AA00",
               "linux64": "#00FF00",
               "osx-10-10": "#0000FF",
               "osx-10-6": "#000055",
               "osx-10-7": "#0000AA",
               "windows7-32": "#AA0000",
               "windows8-64": "#FF0000",
               "windowsxp": "#550000",
               "gecko-decision": "#FF4444"}
    if job["platform"] not in palette:
        print job["platform"]
    return palette.get(job["platform"], "#444444")

def make_plot(repository, revision, data):
    output_file("%s_%s.html" % (repository, revision),
                title="CI Jobs %s %s" % (repository, revision))

    items = data

    p = figure(webgl=True, width=1024, height=20*len(items))

    p.xaxis.axis_label = "time / minutes"
    p.yaxis.bounds = (0, len(data))
    p.yaxis.ticker = None

    for i, (name, jobs) in enumerate(items):
        job = jobs[0]
        offsets = job["offsets"]

        top = len(items) - i - 1
        colour = colours(job)
        p.quad(top=[top], bottom=[top + 1], left=[offsets["pending_start"]],
               right=[offsets["pending_end"]], fill_color=colour, fill_alpha=0.25)
        if "running_start" in offsets:
            p.quad(top=[top], bottom=[top + 1], left=[offsets["running_start"]],
                   right=[offsets["running_end"]], fill_color=colour,
                   fill_alpha=0.5)
        p.text(x=[offsets["pending_start"] + 1], y=[top], text=[job["ref_data_name"]])

    save(p)

def main(repository, revision):
    results_set_data = load_results_set_data(repository, revision)
    results_set_id, push_timestamp = results_set_properties(results_set_data)

    pipeline(results_set_id,
             lambda x: load_jobs_data(repository, x),
             extract_fields,
             filter_tier,
             filter_coalesced,
             lambda x: compute_offsets(push_timestamp, x),
             group_by_type,
             sort_by_id,
             lambda x: make_plot(repository, revision, x)
    )

if __name__ == "__main__":
    main(*sys.argv[1:])
