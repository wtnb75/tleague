import os
import requests
import cachez
import logging
import datetime
from urllib.parse import urljoin
from lxml.html import fromstring
import pytz
import icalendar
import flask

logging.basicConfig(
    format="%(asctime)-15s %(levelname)s %(message)s", level=logging.DEBUG)
app = flask.Flask(__name__)
app.config["JSON_AS_ASCII"] = False
cachez.set_persist_folder("/tmp/cachez")
tzone = pytz.timezone("Asia/Tokyo")


@cachez.persisted(days=30)
def geturl_old(url, args):
    logging.info("fetching(old) %s %s", url, args)
    return requests.get(url, args).content


@cachez.persisted(hours=2)
def geturl_cur(url, args):
    logging.info("fetching(cur) %s %s", url, args)
    return requests.get(url, args).content


@cachez.persisted(hours=10)
def geturl_new(url, args):
    logging.info("fetching(new) %s %s", url, args)
    return requests.get(url, args).content


def geturl(ts, url, args):
    diff = ts - datetime.datetime.now()
    if diff.days > 0:
        return geturl_new(url, args)
    elif diff.days < 0:
        return geturl_old(url, args)
    return geturl_cur(url, args)


class tlgconvert:
    schedule_url = "https://tleague.jp/match/"

    def getdatetime(self, datestr, timestr):
        if timestr == u"未定":
            return datetime.datetime.strptime(datestr, "%Y/%m/%d")
        return datetime.datetime.strptime(datestr+" "+timestr, "%Y/%m/%d %H:%M")

    def read(self):
        trees = []
        t = fromstring(geturl_new(self.schedule_url, {}))
        months = t.find_class("select-month")[0]
        trees.append(t)
        for a in months.xpath(".//a"):
            u = urljoin(self.schedule_url, a.attrib["href"])
            trees.append(fromstring(geturl_new(u, {})))

        teammap = {}
        matches = []
        for tree in trees:
            for cls in ["match-men", "match-women"]:
                for m in tree.find_class(cls):
                    res = {}
                    for k in ["date", "time", "sex", "home", "away", "arena"]:
                        res[k] = m.find_class("cell-"+k)[0].text_content().strip()
                    tmlink = m.find_class("cell-home")[0].xpath(".//a")[0].attrib["href"]
                    tmkey = os.path.basename(os.path.dirname(tmlink))
                    teammap[tmkey] = res["home"]
                    res["home-id"] = tmkey

                    tmlink = m.find_class("cell-away")[0].xpath(".//a")[0].attrib["href"]
                    tmkey = os.path.basename(os.path.dirname(tmlink))
                    teammap[tmkey] = res["away"]
                    res["away-id"] = tmkey

                    rel = m.find_class("cell-result")[0].xpath(".//a")[0].attrib["href"]
                    res["url"] = urljoin(self.schedule_url, rel)
                    res["time"] = res["time"].split()[0]
                    res["date"] = res["date"].split("（")[0]
                    res["datetime"] = self.getdatetime(res["date"], res["time"])
                    diff = res["datetime"]-datetime.datetime.now()
                    if diff.days <= 0:
                        result = fromstring(geturl_old(res["url"], {}))
                        sc = [int(x.text_content().strip())
                              for x in result.find_class("cell-score")]
                        res["homept"] = sc[0]
                        res["awaypt"] = sc[1]
                    matches.append(res)
        self.teammap = teammap
        self.matches = matches

    def convert(self, title, matches):
        ical = icalendar.Calendar()
        ical.add("X-WR-CALNAME", title)
        defval = {"homept": "", "awaypt": ""}
        for m in matches:
            for k, v in defval.items():
                if k not in m:
                    m[k] = v
            ev = icalendar.Event()
            s = "%(home)s %(homept)s-%(awaypt)s %(away)s" % (m)
            ev.add("summary", s)
            st = m["datetime"]
            if st.hour != 0:
                startat = st
                endat = st+datetime.timedelta(hours=2)
            else:
                startat = st.date()
                endat = startat
            ev.add("dtstart", startat)
            ev.add("dtend", endat)
            ev.add("location", "%(arena)s" % (m))
            ev.add("url", "%(url)s" % (m))
            ical.add_component(ev)
        return ical


tlg = tlgconvert()
tlg.read()


@app.route("/<team>.ics")
def getical(team):
    tlg.read()
    if team == "all":
        mts = tlg.matches
        t = "Tリーグ"
    elif team in ("men", "women"):
        tidx = {
            "men": "男子", "women": "女子"
        }
        mts = filter(lambda f: tidx[team] == f["sex"], tlg.matches)
        t = tidx[team]
    elif team in tlg.teammap:
        mts = filter(lambda f: team in (f["home-id"], f["away-id"]), tlg.matches)
        t = tlg.teammap[team]
    else:
        flask.abort(404)
    resp = flask.Response(tlg.convert(t, mts).to_ical().decode(
        "UTF-8"), mimetype="text/calendar")
    return resp


@app.route("/home/<team>.ics")
def getical_home(team):
    tlg.read()
    mts = filter(lambda f: team in (f["home-id"]), tlg.matches)
    if team not in tlg.teammap:
        flask.abort(404)
    t = tlg.teammap[team] + " ホーム"
    resp = flask.Response(tlg.convert(t, mts).to_ical().decode(
        "UTF-8"), mimetype="text/calendar")
    return resp


@app.route("/away/<team>.ics")
def getical_away(team):
    tlg.read()
    mts = filter(lambda f: team in (f["away-id"]), tlg.matches)
    if team not in tlg.teammap:
        flask.abort(404)
    t = tlg.teammap[team] + " アウェイ"
    resp = flask.Response(tlg.convert(t, mts).to_ical().decode(
        "UTF-8"), mimetype="text/calendar")
    return resp


@app.route("/teams.json")
def getteams():
    resp = flask.jsonify(tlg.teammap)
    return resp


@app.route("/")
@app.route("/index.html")
def getindex():
    return flask.render_template("index.j2", data=tlg.teammap)


if __name__ == "__main__":
    # debug = True
    debug = False
    app.run(host="localhost", port=8081, debug=debug, threaded=True)
