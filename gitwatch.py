# Credit to https://github.com/datamachines/gitwatch
import git # gitpython
from datetime import datetime
import yaml # pyaml
import re
import os
import smtplib
from email.mime.text import MIMEText

configfile = "config.yaml"
runfilename = "runfile.yaml"
###############################################################################
# Some functions

# Function for very simple logging capability
def log(message, conf):
    logtime = datetime.now().isoformat()
    try:
        with open(conf['logfile'], "a") as logfile:
            logfile.write(logtime + ' ' + message + '\n')
        logfile.close()
    except IOError:
        print(logtime, "ERROR - Unable to write to logfile.", conf['logfile'])
        exit(1)

# writes our runfile to disk which records the last time of run for idempotency
def write_runfile(run, conf):
    try:
        with open(runfilename, 'w') as runfile:
            runfile.write( yaml.dump(run, default_flow_style=False) )
        runfile.close()
        log("Writing runfile", conf)
    except IOError:
        log("ERROR - Unable to write runfile.", conf)
        exit(1)

# This works with AWS SES. straightforward
def send_smtp_email(email_subject, email_body, conf):
    logtime = datetime.now().isoformat()

    msg = MIMEText(email_body, 'html')
    msg['Subject'] = email_subject
    msg['From'] = conf['smtp_from']
    msg['To'] = conf['smtp_to']
    email_message = msg.as_string()
    try:
        smtpserver = smtplib.SMTP(conf['smtp_server'], int(conf['smtp_port']))
        smtpserver.ehlo()
        smtpserver.starttls()
        smtpserver.login(conf['gmail_username'], conf['gmail_password'])
        smtpserver.sendmail(conf['smtp_from'], conf['smtp_to'], email_message)
        smtpserver.quit()

        log("Emails sent to: " + msg['to'], conf)
    except smtplib.SMTPConnectError:
        log("ERROR - Unable to connect to SMTP server.", conf)
        return 0
    except smtplib.SMTPAuthenticationError:
        log("ERROR - SMTP authentication error.", conf)
        return 0
    return 1

###############################################################################
# Program start

# Set up configuraiton
conf = yaml.safe_load(open(configfile))
# Create the log file if it doesn't exist
try:
    log_file = open(conf['logfile'], 'r')
except IOError:
    log_file = open(conf['logfile'], 'w')

# grab the time of scrip initiialization
now = datetime.now()
init_time = int(now.strftime("%s"))
log("Initialized. Now: " + str(init_time), conf)

# We try to read the runfile to get the last run time. If it doesn't exist
# we create one and exit cleanly.
try:
    run = yaml.safe_load(open(runfilename))
except IOError:
    run = dict(lastrun = int(now.strftime("%s")))
    log("First run, just creating runfile and exiting.", conf)
    log("Tracking new commits from this moment in time: " + now.isoformat(), conf)
    write_runfile(run, conf)
    exit(0)

# If this fails, the program will exit and not send annoying emails.
lastrun = run['lastrun']
run['lastrun'] = init_time
write_runfile(run, conf)

# Check the time and see if it makes sense
log("Last run: " + str(lastrun), conf)
tdelta = init_time - lastrun
log("Time Delta: " + str(tdelta), conf)
if tdelta < 0:
    log("ERROR: Time Delta less than zero. Did the system time change?", conf)
    exit(1)

# Iterate through the commits sending email alerts for commits that have
# happened after the time recorded in our runtime file.
repo = git.Repo(conf['repo_dir'])
commits = list(repo.iter_commits('master'))
ee = re.compile("diff --git a/[a-zA-Z0-9\-]*.md")
for i in range(0,len(commits)):
    commit = commits[i]
    if commit.committed_date > lastrun and commit.committed_date < init_time:
        # Find the modified wiki file
        modifed_file = 'home'
        commit_content = repo.git.show(commits[i])
        try:
            modifed_file = re.findall(ee, commit_content)[0] \
                .split('/')[-1] \
                .split('.')[0].lower()
        except:
            log("Error when finding file name.", conf)
        url = conf['wiki_url'] + modifed_file

        # Construct the email
        subject = "[" + conf['smtp_subject'] + " to " + modifed_file + "] by " \
            + commit.author.name 

        body = "<html>\n" \
            + "The modified file can be found <a href=\"" + url + "\">" \
            + "here." + "</a><br><br>\n\n" \
            + "The following modifications were made:<br>\n" \
            + "\n\n<pre>\n" + repo.git.show(commits[i])  \
            + "\n</pre>\n<br><br>\n\n" \
            + "Your Friendly Wiki-Bot<br>" \
            + " <a href=\"" + conf['wiki_url'] + "home" + "\">" \
            + "Wiki Home" + "</a><br><br>\n\n" \
            + "</html>"
        
        # Send the email to the 
        send_smtp_email(subject, body, conf)

# Write the atomic initialization time to the runfile and then exit cleanly.
exit(0)
