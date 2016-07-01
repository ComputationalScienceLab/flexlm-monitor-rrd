# Flexlm Monitor with RRD

## Description
This is flask app for monitoring Flexlm servers. You can specify an rdd file and 
the columns you want then plot the results as a d3 chart. You will need to set up
the rrd file and collect the usage data from the flexlm server.

Requirments
lmutil, python, rrdtool, sqlite

## Setup
In the file flexlm_parser.py check the following line and make sure that is 
matches the location of the lmutil binary.

```
# May have to change this line to the path to lmutil
lmutil = "/usr/local/bin/lmutil"
```

Run the add_user script this will prompt you for a user name and a password.

```
python add_user.py
```

This will add a new user to the web application.
By logging onto the webapplication you will be able to add and confiure
flexlm servers and select an rrd files through the web application.
No logon is required to view the current users or usage graphs.


To install the nessary python packages
```
pip install -r requirements.txt
```
In flexlm_app.py:
```
app = Flask(__name__)
app.config['SECRET_KEY'] = 'hard to guess string'
```
Change the SECRET_KEY value in the flex_app.py from "hard to guess string" 
to a string that would be difficult to guess.

To run the application
```
python flexlm_app.py runserver
```

point your browser at: http://localhost:5000/

Once you have added a server you can check on the current users and a 
view a usage chart if you have added an rrd file to the server.

You can also specify a time peroid by using the following URL syntax

```
http://localhost:5000/servers/usage/<server name>/<time peroid>

e.g. 
http://localhost:5000/servers/usage/my_server/1y
```

The corrosponding json end point is
http://localhost:5000/servers/usage/data/my_server/1y

The application was orginally written to replace somthing that I had written in 
the past that worked but was not that portable. It was also developed to try 
out flask. Hence could most probably be structured a little bit better. 

## Credits
[Glyphicons](http://glyphicons.com)

Miguel Grinberg book [Flask web development](http://shop.oreilly.com/product/0636920031116.do)

beaugunderson 
[flexlm-license-status script](https://github.com/beaugunderson/flexlm-license-status)



