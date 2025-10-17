# Tutorial To Generate Simulations

1. Open **netedit.exe** and start creating a network (I chose a grid to represent Manhattan, everything is easily adaptable, just gotta add or delete nodes and edges)

2. Manually create routes in netedit (easier because we don't need any know-how as to determine edge IDs, which is very annoying) and save to the routes file

3. Use the command `duarouter -n YOUR_NETWORK.net.xml -t YOUR_NETEDIT_ROUTES_FILE.rou.xml -o routes.rou.xml` to generate route files with edge IDs

4. Define flows based on your manually created routes and vehicle types, for example:

    - ```xml
        <?xml version="1.0" encoding="UTF-8"?>
        <routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">

            <!-- Vehicle Type (considers emissions) -->
            <vType id="car" length="4.50" minGap="2.50" maxSpeed="13.90" emissionClass="HBEFA3/PC_G_EU6" guiShape="passenger" color="red" accel="2.6" decel="4.5" sigma="0.5"/>

            <!-- Flow 1: A4B4 -> E2D2, one vehicle every 6 seconds -->
            <route id="r_upper" edges="A4B4 B4C4 C4D4 D4E4 E4E3 E3E2 E2D2"/>
            <flow id="flow_0" type="car" begin="0" end="3600" period="6.0" route="r_upper"/>

        </routes>

5. Convert the xml files to csv for ease of use through:

    - python "C:\Program Files (x86)\Eclipse\Sumo\tools\xml\xml2csv.py" emissions.xml

    5.1. **VERY IMPORTANT**: xml2csv separates with ";" instead of ",": 
    ```python
     df = pd.read_csv(r"..\outputs\emissions.csv", sep=";") 
     ```


6. Assuming the vehicle ID's are numbered starting from 0, placed as flow ID + ".vehicle_in_order_of_spawn", we should order the csv in a descending manner based on said vehicles, in order to ascertain individual average pollution (all done in `preprocess.ipynb`)

