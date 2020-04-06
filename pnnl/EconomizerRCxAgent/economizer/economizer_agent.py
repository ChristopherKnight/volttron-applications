
import sys
import logging
from datetime import timedelta as td
from dateutil import parser
from volttron.platform.agent import utils
from volttron.platform.messaging import topics
from volttron.platform.agent.math_utils import mean
from volttron.platform.agent.utils import setup_logging
from volttron.platform.vip.agent import Agent, Core

from . import constants
from . diagnostics.TemperatureSensor import TemperatureSensor
from . diagnostics.EconCorrectlyOn import EconCorrectlyOn
from . diagnostics.EconCorrectlyOff import EconCorrectlyOff
from . diagnostics.ExcessOutsideAir import ExcessOutsideAir
from . diagnostics.InsufficientOutsideAir import InsufficientOutsideAir

__version__ = "1.2.0"

setup_logging()
_log = logging.getLogger(__name__)

class EconomizerAgent(Agent):

    def __init__(self, config_path, **kwargs):
        super(EconomizerAgent, self).__init__(**kwargs)

        #list of class attributes.  Default values will be filled in from reading config file
        #string attributes
        self.campus = ""
        self.building = ""
        self.agent_id = ""
        self.device_type = ""
        self.economizer_type = ""
        self.sensitivity = ""
        self.analysis_name = ""
        self.fan_status_name = ""
        self.fan_sp_name = ""
        self.oat_name = ""
        self.rat_name = ""
        self.mat_name = ""
        self.oad_sig_name = ""
        self.cool_call_name = ""

        #list attributes
        self.device_list = []
        self.units = []
        self.arguments = []
        self.point_mapping = []
        self.damper_data = []
        self.oat_data = []
        self.mat_data = []
        self.rat_data = []
        self.cooling_data = []
        self.fan_sp_data = []
        self.fan_status_data = []
        self.missing_data = []

        #int attributes
        self.data_window = 0
        self.no_required_data = 0
        self.open_damper_time = 0
        self.fan_speed = 0

        #bool attributes
        self.constant_volume = False

        #float attributes
        self.econ_hl_temp = 0.0
        self.temp_band = 0.0
        self.oaf_temperature_threshold = 0.0
        self.oaf_economizing_threshold = 0.0
        self.cooling_enabled_threshold = 0.0
        self.temp_difference_threshold = 0.0
        self.mat_low_threshold = 0.0
        self.mat_high_threshold = 0.0
        self.rat_low_threshold = 0.0
        self.rat_high_threshold = 0.0
        self.oat_low_threshold = 0.0
        self.oat_high_threshold = 0.0
        self.oat_mat_check = 0.0
        self.open_damper_threshold = 0.0
        self.minimum_damper_setpoint = 0.0
        self.desired_oaf = 0.0
        self.low_supply_fan_threshold = 0.0
        self.excess_damper_threshold = 0.0
        self.excess_oaf_threshold = 0.0
        self.ventilation_oaf_threshold = 0.0
        self.insufficient_damper_threshold = 0.0
        self.temp_damper_threshold = 0.0
        self.rated_cfm = 0.0
        self.eer = 0.0
        self.temp_deadband = 0.0
        self.oat = 0.0
        self.rat = 0.0
        self.mat = 0.0
        self.oad = 0.0

        # Precondition flags
        self.oaf_condition = None
        self.unit_status = None
        self.sensor_limit = None
        self.temp_sensor_problem = None

        #diagnostics
        self.temp_sensor = None
        self.econ_correctly_on = None
        self.econ_correctly_off = None
        self.excess_outside_air = None
        self.insufficient_outside_air = None

        #start reading all the class configs and check them
        self.read_config(config_path)
        self.read_argument_config(config_path)
        self.read_point_mapping()
        self.configuration_value_check()
        self.create_diagnostics()


    def read_config(self, config_path):
        """
        Use volttrons config reader to grab and parse out configuration file
        :param config_path: The path to the agents configuration file
        """
        config = utils.load_config(config_path)
        #get device, then the units underneath that
        self.analysis_name = config.get("analysis_name", "analysis_name")
        self.device = config.get("device", {})
        if "campus" in self.device:
            self.campus = self.device["campus"]
        if "building" in self.device:
            self.building = self.device["building"]
        if "unit" in self.device:
            #units will be a dictionary with subdevices
            self.units = self.device["unit"]
        for u in self.units:
            #building the connection string for each unit
            _log.info("unit is:" + str(u))
            self.device_list.append(topics.DEVICES_VALUE(campus=self.campus, building=self.building, unit=u, path="", point="all"))
            #loop over subdevices and add them
            if "subdevices" in self.units[u]:
                for sd in self.units[u]["subdevices"]:
                    self.device_list.append(topics.DEVICES_VALUE(campus=self.campus, building=self.building, unit=u, path=sd, point="all"))

    def read_argument_config(self, config_path):
        """read all the config arguments section"""
        config = utils.load_config(config_path)
        self.arguments = config.get("arguments", {})

        self.econ_hl_temp = self.read_argument("econ_hl_temp", 65.0)
        self.constant_volume = self.read_argument("constant_volume", False)
        self.temp_band = self.read_argument("temp_band", 1.0)
        self.oaf_temperature_threshold = self.read_argument("oaf_temperature_threshold", 5.0)
        self.oaf_economizing_threshold = self.read_argument("oaf_economizing_threshold", 25.0)
        self.cooling_enabled_threshold = self.read_argument("cooling_enabled_threshold", 5.0)
        self.temp_difference_threshold = self.read_argument("temp_difference_threshold", 4.0)
        self.mat_low_threshold = self.read_argument("mat_low_threshold", 50.0)
        self.mat_high_threshold = self.read_argument("mat_high_threshold", 90.0)
        self.rat_low_threshold = self.read_argument("rat_low_threshold", 50.0)
        self.rat_high_threshold = self.read_argument("rat_high_threshold", 90.0)
        self.oat_low_threshold = self.read_argument("oat_low_threshold", 30.0)
        self.oat_high_threshold = self.read_argument("oat_high_threshold", 110.0)
        self.oat_mat_check = self.read_argument("oat_mat_check", 5.0)
        self.open_damper_threshold = self.read_argument("open_damper_threshold", 80.0)
        self.minimum_damper_setpoint = self.read_argument("minimum_damper_setpoint", 20.0)
        self.desired_oaf = self.read_argument("desired_oaf", 10.0)
        self.low_supply_fan_threshold = self.read_argument("low_supply_fan_threshold", 15.0)
        self.excess_damper_threshold = self.read_argument("excess_damper_threshold", 20.0)
        self.excess_oaf_threshold = self.read_argument("excess_oaf_threshold", 20.0)
        self.ventilation_oaf_threshold = self.read_argument("ventilation_oaf_threshold", 5.0)
        self.insufficient_damper_threshold = self.read_argument("insufficient_damper_threshold", 15.0)
        self.temp_damper_threshold = self.read_argument("temp_damper_threshold", 90.0)
        self.rated_cfm = self.read_argument("rated_cfm", 6000.0)
        self.eer = self.read_argument("eer", 10.0)
        self.temp_deadband = self.read_argument("temp_deadband", 1.0)
        self.data_window = td(minutes=self.read_argument("data_window", 30))
        self.no_required_data = self.read_argument("no_required_data", 15)
        self.open_damper_time = td(minutes=self.read_argument("open_damper_time", 5))
        self.device_type = self.read_argument("device_type", "rtu").lower()
        self.economizer_type = self.read_argument("economizer_type", "DDB").lower()
        self.sensitivity = self.read_argument("sensitivity", ['low', 'normal', 'high'])
        self.point_mapping = self.read_argument("point_mapping", {})

    def read_argument(self, config_key, default_value):
        """Method that reads an argument from the config file and returns the value or returns the default value if key is not present in config file"""
        return_value = default_value
        if config_key in self.arguments:
            return_value = self.arguments[config_key]
        return return_value

    def read_point_mapping(self):
        """Method that reads the point mapping and sets the values"""
        self.fan_status_name = self.get_point_mapping_or_none("supply_fan_status")
        self.fan_sp_name = self.get_point_mapping_or_none("supply_fan_speed")
        self.oat_name = self.get_point_mapping_or_none("outdoor_air_temperature")
        self.rat_name = self.get_point_mapping_or_none("return_air_temperature")
        self.mat_name = self.get_point_mapping_or_none("mixed_air_temperature")
        self.oad_sig_name = self.get_point_mapping_or_none("outdoor_damper_signal")
        self.cool_call_name = self.get_point_mapping_or_none("cool_call")

    def get_point_mapping_or_none(self, name):
        value = self.point_mapping.get(name, None)
        return value

    def configuration_value_check(self):
        """Method goes through the configuration values and checks them for correctness.  Will error if values are not correct. Some may change based on specific settings"""
        if self.sensitivity is not None and self.sensitivity == "custom":
            self.oaf_temperature_threshold = max(5.0, min(self.oaf_temperature_threshold, 15.0))
            self.cooling_enabled_threshold = max(5.0, min(self.cooling_enabled_threshold, 50.0))
            self.temp_difference_threshold = max(2.0, min(self.temp_difference_threshold, 6.0))
            self.mat_low_threshold = max(40.0, min(self.mat_low_threshold, 60.0))
            self.mat_high_threshold = max(80.0, min(self.mat_high_threshold, 90.0))
            self.rat_low_threshold = max(40.0, min(self.rat_low_threshold, 60.0))
            self.rat_high_threshold = max(80.0, min(self.rat_high_threshold, 90.0))
            self.oat_low_threshold = max(20.0, min(self.oat_low_threshold, 40.0))
            self.oat_high_threshold = max(90.0, min(self.oat_high_threshold, 125.0))
            self.open_damper_threshold = max(60.0, min(self.open_damper_threshold, 90.0))
            self.minimum_damper_setpoint = max(0.0, min(self.minimum_damper_setpoint, 50.0))
            self.desired_oaf = max(5.0, min(self.desired_oaf, 30.0))
        else:
            self.oaf_temperature_threshold = 5.0
            self.cooling_enabled_threshold = 5.0
            self.temp_difference_threshold = 4.0
            self.mat_low_threshold = 50.0
            self.mat_high_threshold = 90.0
            self.rat_low_threshold = 50.0
            self.rat_high_threshold = 90.0
            self.oat_low_threshold = 30.0
            self.oat_high_threshold = 110.0
            self.open_damper_threshold = 80.0
            self.minimum_damper_setpoint = 20.0
            self.desired_oaf = 10.0

        if self.economizer_type == "hl":
            self.econ_hl_temp = max(50.0, min(self.econ_hl_temp, 75.0))
        else:
            self.econ_hl_temp = None
        self.temp_band = max(0.5, min(self.temp_band, 10.0))
        if self.device_type not in ("ahu", "rtu"):
            _log.error('device_type must be specified as "AHU" or "RTU" in configuration file.')
            sys.exit()

        if self.economizer_type.lower() not in ("ddb", "hl"):
            _log.error('economizer_type must be specified as "DDB" or "HL" in configuration file.')
            sys.exit()

        if self.fan_sp_name is None and self.fan_status_name is None:
            _log.error("SupplyFanStatus or SupplyFanSpeed are required to verify AHU status.")
            sys.exit()

    def create_diagnostics(self):
        """creates the diagnostic classes"""
        self.temp_sensor = TemperatureSensor()
        self.temp_sensor.set_class_values(self.analysis_name, self.data_window, self.no_required_data, self.temp_difference_threshold, self.open_damper_time,  self.temp_damper_threshold)
        self.econ_correctly_on = EconCorrectlyOn()
        self.econ_correctly_on.set_class_values(self.analysis_name, self.open_damper_threshold, self.minimum_damper_setpoint, self.data_window, self.no_required_data, float(self.rated_cfm), self.eer)
        self.econ_correctly_off = EconCorrectlyOff()
        self.econ_correctly_off.set_class_values(self.analysis_name, self.data_window, self.no_required_data, self.minimum_damper_setpoint, self.desired_oaf, float(self.rated_cfm), self.eer)
        self.excess_outside_air = ExcessOutsideAir()
        self.excess_outside_air.set_class_values(self.analysis_name, self.data_window, self.no_required_data, self.minimum_damper_setpoint, self.desired_oaf, float(self.rated_cfm), self.eer)
        self.insufficient_outside_air = InsufficientOutsideAir()
        self.insufficient_outside_air.set_class_values(self.analysis_name, self.data_window, self.no_required_data, self.desired_oaf)

    def parse_data_message(self, message):
        """Breaks down the passed VOLTTRON message"""
        data_message = message[0]
        #reset the data arrays on new message
        self.fan_status_data = []
        self.damper_data = []
        self.oat_data = []
        self.mat_data = []
        self.rat_data = []
        self.cooling_data = []
        self.fan_sp_data = []
        self.missing_data = []

        for key in data_message:
            value = data_message[key]
            if value is None:
                continue
            if key == self.fan_status_name:
                self.fan_status_data.append(value)
            elif key == self.oad_sig_name:
                self.damper_data.append(value)
            elif key == self.oat_name:
                self.oat_data.append(value)
            elif key == self.mat_name:
                self.mat_data.append(value)
            elif key == self.rat_name:
                self.rat_data.append(value)
            elif key == self.cool_call_name:
                self.cooling_data.append(value)
            elif key == self.fan_sp_name:
                self.fan_sp_data.append(value)


    def check_for_missing_data(self):
        """Method that checks the parsed message results for any missing data"""
        if not self.oat_data:
            self.missing_data.append(self.oat_name)
        if not self.rat_data:
            self.missing_data.append(self.rat_name)
        if not self.mat_data:
            self.missing_data.append(self.mat_name)
        if not self.damper_data:
            self.missing_data.append(self.oad_sig_name)
        if not self.cooling_data:
            self.missing_data.append(self.cool_call_name)
        if not self.fan_status_data and not self.fan_sp_data:
            self.missing_data.append(self.fan_status_name)

        if self.missing_data:
            return True
        return False

    def check_fan_status(self, current_time):
        """Check the status and speed of the fan"""
        if self.fan_status_data:
            supply_fan_status = int(max(self.fan_status_data))
        else:
            supply_fan_status = None

        if self.fan_sp_data:
            self.fan_speed = mean(self.fan_sp_data)
        else:
            self.fan_speed = None
        if supply_fan_status is None:
            if self.fan_speed > self.low_supply_fan_threshold:
                supply_fan_status = 1
            else:
                supply_fan_status = 0

        if not supply_fan_status:
            if self.unit_status is None:
                self.unit_status = current_time
        else:
            self.unit_status = None
        return supply_fan_status

    def check_temperature_condition(self, current_time):
        """Ensure the OAT and RAT have minimum difference to allow for a conclusive diagnostic."""
        if abs(self.oat - self.rat) < self.oaf_temperature_threshold:
            if self.oaf_condition is None:
                self.oaf_condition = current_time
        else:
            self.oaf_condition = None

    def check_elapsed_time(self, current_time, condition, message):
        """Check on time since last message to see if it is in data window"""
        if condition is not None:
            elapsed_time = current_time - condition
        else:
            elapsed_time = td(minutes=0)
        if elapsed_time >= self.data_window:
            self.pre_conditions(message, current_time)
            self.clear_all()

    def clear_all(self):
        """Reinitialize all data arrays for diagnostics."""
        self.clear_diagnostics()
        self.temp_sensor_problem = None
        self.unit_status = None
        self.oaf_condition = None
        self.sensor_limit = None

    def clear_diagnostics(self):
        """Clear the diagnositcs"""
        self.temp_sensor.clear_data()
        self.econ_correctly_on.clear_data()
        self.econ_correctly_off.clear_data()
        self.excess_outside_air.clear_data()
        self.insufficient_outside_air.clear_data()
        pass

    def pre_conditions(self, message, cur_time):
        """Publish Pre conditions not met"""
        dx_msg = {}
        for sensitivity in self.sensitivity:
            dx_msg[sensitivity] = message

        for diagnostic in constants.DX_LIST:
            _log.info(constants.table_log_format(self.analysis_name, cur_time, (diagnostic + constants.DX + ':' + str(dx_msg))))

    def sensor_limit_check(self, current_time):
        """ Check temperature limits on sensors."""
        sensor_limit = (False, None)
        if self.oat < self.oat_low_threshold or self.oat > self.oat_high_threshold:
            sensor_limit = (True, constants.OAT_LIMIT)
        elif self.mat < self.mat_low_threshold or self.mat > self.mat_high_threshold:
            sensor_limit = (True, constants.MAT_LIMIT)
        elif self.rat < self.rat_low_threshold or self.rat > self.rat_high_threshold:
            sensor_limit = (True, constants.RAT_LIMIT)

        if sensor_limit[0]:
            if self.sensor_limit is None:
                self.sensor_limit = current_time
        else:
            self.sensor_limit = None
        return sensor_limit

    def determine_cooling_condition(self):
        """Determine if the unit is in a cooling mode and if conditions are favorable for economizing."""
        if self.device_type == "ahu":
            clg_vlv_pos = mean(self.cooling_data)
            cool_call = True if clg_vlv_pos > self.cooling_enabled_threshold else False
        elif self.device_type == "rtu":
            cool_call = int(max(self.cooling_data))

        if self.economizer_type == "ddb":
            econ_condition = (self.rat - self.oat) > self.temp_band
        else:
            econ_condition = (self.econ_hl_temp - self.oat) > self.temp_band

        return econ_condition, cool_call


    @Core.receiver("onstart")
    def onstart_subscriptions(self, sender, **kwargs):
        """Method used to setup data subscription on startup of the agent"""
        for device in self.device_list:
            _log.info("Subscribing to " + device)
            self.vip.pubsub.subscribe(peer="pubsub", prefix=device, callback=self.new_data_message)


    def new_data_message(self, peer, sender, bus, topic, headers, message):
        """
        Call back method for curtailable device data subscription.
        :param peer:
        :param sender:
        :param bus:
        :param topic:
        :param headers:
        :param message:
        :return:
        """
        current_time = parser.parse(headers["Date"])
        _log.info("Processing Results!")
        self.parse_data_message(message)
        missing_data = self.check_for_missing_data()
        #want to do no further parsing if data is missing
        if missing_data:
            _log.info("Missing data from publish: {}".format(self.missing_data))
            return

        #check on fan status and speed
        fan_status = self.check_fan_status(current_time)
        self.check_elapsed_time(current_time, self.unit_status, constants.FAN_OFF)
        if not fan_status:
            _log.info("Supply fan is off: {}".format(current_time))
            return
        else:
            _log.info("Supply fan is on: {}".format(current_time))

        if self.fan_speed is None and self.constant_volume:
            self.fan_speed = 100.0

        self.oat = mean(self.oat_data)
        self.rat = mean(self.rat_data)
        self.mat = mean(self.mat_data)
        self.oad = mean(self.damper_data)

        #check on temperature condition
        self.check_temperature_condition(current_time)
        self.check_elapsed_time(current_time, self.oaf_condition, constants.OAF)

        if self.oaf_condition:
            _log.info("OAT and RAT readings are too close.")
            return

        limit_condition = self.sensor_limit_check(current_time)
        self.check_elapsed_time(current_time, self.sensor_limit, limit_condition[1])
        #check to see if there was a temperature sensor out of bounds
        if limit_condition[0]:
            _log.info("Temperature sensor is outside of bounds: {} -- {}".format(limit_condition, self.sensor_limit))
            return

        self.temp_sensor_problem = self.temp_sensor.temperature_algorithm(self.oat, self.rat, self.mat, self.oad, current_time)
        econ_condition, cool_call = self.determine_cooling_condition()
        _log.debug("Cool call: {} - Economizer status: {}".format(cool_call, econ_condition))

        if self.temp_sensor_problem is not None and not self.temp_sensor_problem:
            self.econ_correctly_on.economizer_on_algorithm(cool_call, self.oat, self.rat, self.mat, self.oad, econ_condition, current_time, self.fan_speed)
            self.econ_correctly_off.economizer_off_algorithm(self.oat, self.rat, self.mat, self.oad, econ_condition, current_time, self.fan_speed)
            self.excess_outside_air.excess_ouside_air_algorithm(self.oat, self.rat, self.mat, self.oad, econ_condition, current_time, self.fan_speed)
            self.insufficient_outside_air.insufficient_outside_air_algorithm(self.oat, self.rat, self.mat, current_time)
        elif self.temp_sensor_problem:
            self.pre_conditions(constants.TEMP_SENSOR, current_time)
            self.clear_diagnostics()


def main(argv=sys.argv):
    """Main method called by the app."""
    try:
        utils.vip_main(EconomizerAgent)
    except Exception as exception:
        _log.exception("unhandled exception")
        _log.error(repr(exception))


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
