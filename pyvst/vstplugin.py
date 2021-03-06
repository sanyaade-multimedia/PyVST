import numpy
import struct
from ctypes import CDLL, POINTER

from aeffect import *
from aeffectx import *


#===============================================================================
kVstVersion = 2400


#===============================================================================
def basic_callback(effect, opcode, index, value, ptr, opt):
    """
    Basic callback
    """
    if opcode == AudioMasterOpcodes.audioMasterVersion:
        return kVstVersion
    return 0


#===============================================================================
class VSTPlugin(object):
    """
    An actual VST plugin wrapper
    """
    def __init__(self, filename, audio_callback = basic_callback):
        """
        Constructor
        Parameters:
          filename is the name of the plugin to load
          audio_callback is the Python function to call (optional)
        """
        self.__lib = CDLL(filename)
        self.__callback = audiomaster_callback(audio_callback)

        try:
            self.__lib.VSTPluginMain.argtypes = [audiomaster_callback, ]
            self.__lib.VSTPluginMain.restype = POINTER(AEffect)
            self.__effect = self.__lib.VSTPluginMain(self.__callback).contents
        except AttributeError:
            self.__lib.main.argtypes = [audiomaster_callback, ]
            self.__lib.main.restype = POINTER(AEffect)
            self.__effect = self.__lib.main(self.__callback).contents

        self.__populate_methods()
  
    def __populate_methods(self):
        """
        @Internal
        """
        self.dispatcher = create_dispatcher_proc(self.__effect.dispatcher)
        self.__process_replacing = create_process_proc(self.__effect.processReplacing)
        if(self.__effect.processDoubleReplacing):
            self.__process_double_replacing = create_process_double_proc(self.__effect.processDoubleReplacing)
        self.__set_param = create_set_param_proc(self.__effect.setParameter)
        self.__get_param = create_get_param_proc(self.__effect.getParameter)

    # properties ---------------------------------------------------------------
    def get_name(self):
        name = c_char_p('\0' * VstStringConstants.kVstMaxEffectNameLen)
        self.dispatcher(byref(self.__effect), AEffectXOpcodes.effGetEffectName, 0, 0, name, 0.)
        return name.value

    def get_vendor(self):
        name = c_char_p('\0' * VstStringConstants.kVstMaxVendorStrLen)
        self.dispatcher(byref(self.__effect), AEffectXOpcodes.effGetVendorString, 0, 0, name, 0.)
        return name.value

    def get_vendor_version(self):
        name = c_char_p('\0' * VstStringConstants.kVstMaxVendorStrLen)
        self.dispatcher(byref(self.__effect), AEffectXOpcodes.effGetVendorVersion, 0, 0, name, 0.)
        return name.value

    def get_version(self):
        return self.__effect.version

    def get_product(self):
        name = c_char_p('\0' * VstStringConstants.kVstMaxProductStrLen)
        self.dispatcher(byref(self.__effect), AEffectXOpcodes.effGetProductString, 0, 0, name, 0.)
        return name.value

    def is_synth(self):
        return (self.__effect.flags & VstAEffectFlags.effFlagsIsSynth) == VstAEffectFlags.effFlagsIsSynth

    def no_tail(self):
        return (self.__effect.flags & VstAEffectFlags.effFlagsNoSoundInStop) == VstAEffectFlags.effFlagsNoSoundInStop

    def can_receive_events(self):
        return self.can_do("receiveVstEvents") and self.can_do("receiveVstMidiEvent")

    def can_receive_timeinfo(self):
        return self.can_do("receiveVstTimeInfo")

    def can_do(self, what):
        what = c_char_p(what + '\0')
        return self.dispatcher(byref(self.__effect), AEffectXOpcodes.effCanDo, 0, 0, what, 0.) == 1

    def can_process_double(self):
        return (self.__effect.flags & VstAEffectFlags.effFlagsCanDoubleReplacing) == VstAEffectFlags.effFlagsCanDoubleReplacing

    # setup --------------------------------------------------------------------
    def open(self):
        """
        Open plugin
        """
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effOpen, 0, 0, None, 0)

    def close(self):
        """
        Close plugin
        """
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effClose, 0, 0, None, 0)

    def suspend(self):
        """
        Suspend plugin
        """
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effMainsChanged, 0, 0, None, 0.)

    def resume(self):
        """
        Resume plugin
        """
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effMainsChanged, 0, 1, None, 0.)

    def set_sample_rate(self, sample_rate):
        """
        Change samplerate of plugin
        """
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effSetSampleRate, 0, 0, None, sample_rate)

    def set_block_size(self, block_size):
        """
        Set block size of plugin
        """
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effSetBlockSize, 0, block_size, None, 0)

    # processing----------------------------------------------------------------
    def process_replacing(self, inputs, outputs, sample_frames):
        """
        Normal process replacing function
        """
        f4ptr = POINTER(c_float)
        float_input_pointers = (f4ptr*len(inputs))(*[row.ctypes.data_as(f4ptr) for row in inputs])
        float_output_pointers = (f4ptr*len(outputs))(*[row.ctypes.data_as(f4ptr) for row in outputs])
        self.__process_replacing(byref(self.__effect), float_input_pointers, float_output_pointers, sample_frames)

    def process_double_replacing(self, inputs, outputs, sample_frames):
        """
        Normal process replacing function with doubles
        """
        d4ptr = POINTER(c_double)
        double_input_pointers = (d4ptr*len(inputs))(*[row.ctypes.data_as(d4ptr) for row in inputs])
        double_output_pointers = (d4ptr*len(outputs))(*[row.ctypes.data_as(d4ptr) for row in outputs])
        self.__process_double_replacing(byref(self.__effect), double_input_pointers, double_output_pointers, sample_frames)
      
    def process_note_events(self, events, block_size):
        """
        Convenience function to pass directly bytes to process events
        """
        if len(events) > 0:
            thisEvents = [e for e in events if e[3] < block_size]
            VstMidiEventArray = VstMidiEvent * len(thisEvents)
            vstMidiEvents = VstMidiEventArray()
            for idx in xrange(0, len(thisEvents)):
                e = thisEvents[idx]
                mev = vstMidiEvents[idx]
                mev.type = VstEventTypes.kVstMidiType
                mev.byteSize = c_int(sizeof(VstMidiEvent))
                mev.deltaFrames = c_int(e[3])
                mev.flags = c_int(0)
                mev.noteLength = c_int(0)
                mev.noteOffset = c_int(0)
                mev.midiData = chr(e[0]) + chr(e[1]) + chr(e[2]) + chr(0x00)
                mev.detune = chr(0)
                mev.noteOffVelocity = chr(0)
                mev.reserved1 = chr(0)
                mev.reserved2 = chr(0)
            self.process_events(vstMidiEvents)
        return [(e[0], e[1], e[2], e[3] - block_size) for e in events if e[3] - block_size >= 0]

    def process_events(self, events):
        """
        Real process events call
        """
        if len(events) > 0:
            midiEvents = VstEvents()
            midiEvents.numEvents = len(events)
            midiEvents.reserved = c_void_p(0)
            midiEvents.events = (POINTER(VstEvent) * 2)(cast(VstMidiEventPtr(events), VstEventPtr), cast(c_void_p(0), VstEventPtr))
            self.dispatcher(byref(self.__effect), AEffectXOpcodes.effProcessEvents, 0, 0, byref(midiEvents), 0.)

    # parameters ---------------------------------------------------------------
    def get_number_of_parameters(self):
        """
        Number of parameters
        """
        return self.__effect.numParams
    number_of_parameters = property(get_number_of_parameters)

    def set_parameter(self, index, value):
        """
        Set plugin parameter
        """
        return self.__set_param(byref(self.__effect), index, value)
      
    def get_parameter(self, index):
        """
        Get plugin parameter
        """
        return self.__get_param(byref(self.__effect), index)

    def get_parameter_name(self, index):
        """
        Get plugin parameter name
        """
        name = c_char_p('\0' * VstStringConstants.kVstExtMaxParamStrLen)
        self.dispatcher(byref(self.__effect), AEffectOpcodes.effGetParamName, index, 0, name, 0.)
        return name.value

    def get_parameter_label(self, index):
        """
        Get plugin parameter label
        """
        name = c_char_p('\0' * VstStringConstants.kVstExtMaxParamStrLen)
        self.dispatcher(byref(self.__effect), AEffectOpcodes.effGetParamLabel, index, 0, name, 0.)
        return name.value

    def get_parameter_display(self, index):
        """
        Get plugin parameter display
        """
        name = c_char_p('\0' * VstStringConstants.kVstExtMaxParamStrLen)
        self.dispatcher(byref(self.__effect), AEffectOpcodes.effGetParamDisplay, index, 0, name, 0.)
        return name.value

    # programs -----------------------------------------------------------------
    def get_number_of_programs(self):
        """
        Number of programs
        """
        return self.__effect.numPrograms
    number_of_programs = property(get_number_of_programs)

    def get_program_name_indexed(self, index):
        """
        Get name of indexed program
        """
        name = c_char_p('\0' * VstStringConstants.kVstMaxProgNameLen)
        if self.dispatcher(byref(self.__effect), AEffectXOpcodes.effGetProgramNameIndexed, index, 0, name, 0.):
            raise IndexError("No program with this index (%d)" % index)
        return name.value

    def get_program(self):
        """
        Get program index number
        """
        retval = self.dispatcher(byref(self.__effect), AEffectOpcodes.effGetProgram, 0, 0, None, 0.)
        #retval = cast(pointer(plugin.get_program()), POINTER(c_void_p)).contents.value
        return retval

    def set_program(self, index):
        """
        Set program index number
        """
        self.dispatcher(byref(self.__effect), AEffectOpcodes.effSetProgram, index, 0, None, 0.)

    def get_program_name(self):
        """
        Get name of current program
        """
        name = c_char_p('\0' * VstStringConstants.kVstMaxProgNameLen)
        self.dispatcher(byref(self.__effect), AEffectOpcodes.effGetProgramName, 0, 0, name, 0.)
        return name.value

    def get_chunk(self):
        """
        Get chunk of data (save)
        """
        data = c_void_p(0)
        byte_size = self.dispatcher(byref(self.__effect), AEffectOpcodes.effGetChunk, 0, 0, byref(data), 0.)
        dest_data = []
        src_data = cast(data, POINTER(c_ubyte))
        for b in xrange(byte_size):
            dest_data.append(struct.pack('B', src_data[b]))
        return dest_data

    def set_chunk(self, data):
        """
        Set chunk of data (load)
        """
        byte_size = len(data)
        dest_data = (c_ubyte * (byte_size + 1))()
        for b in xrange(byte_size):
            dest_data[b] = c_ubyte(ord(data[b]))
        byte_size = self.dispatcher(byref(self.__effect), AEffectOpcodes.effSetChunk, 0, byte_size, byref(dest_data), 0.)

    # input/output/latency -----------------------------------------------------
    def get_number_of_inputs(self):
        return self.__effect.numInputs
    number_of_inputs = property(get_number_of_inputs)

    def get_number_of_outputs(self):
        return self.__effect.numOutputs
    number_of_outputs = property(get_number_of_outputs)

    def get_latency(self):
        return self.__effect.initialDelay
    latency = property(get_latency)

    # editor -------------------------------------------------------------------
    def has_editor(self):
        return (self.__effect.flags & VstAEffectFlags.effFlagsHasEditor) == VstAEffectFlags.effFlagsHasEditor

    def open_edit(self, window = None):
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effEditOpen, 0, 0, window, 0)

    def close_edit(self):
        return self.dispatcher(byref(self.__effect), AEffectOpcodes.effEditClose, 0, 0, None, 0)
      
    def get_erect(self):
        rect = POINTER(ERect)()
        self.dispatcher(byref(self.__effect), AEffectOpcodes.effEditGetRect, 0, 0, byref(rect), 0)
        return rect.contents

    def open_gui(self):
        """
        Convenience function to open gui
        """
        if self.has_editor():
            import vstgui
            vstgui.raise_gui(self)
            #thread = vstgui.PluginWindowThread(self)
            #thread.start()
            #thread.join()

    # dump ---------------------------------------------------------------------
    def dump_properties(self, show_params=True, show_programs=True):
        """
        Dump on the screen every thing about the effect properties
        """
        print "Plugin name:", self.get_name()
        print "Vendor name:", self.get_vendor()
        print "Product name:", self.get_product()

        print "numInputs: %d" % self.number_of_inputs
        print "numOutputs: %d" % self.number_of_outputs
        print "numParams: %d" % self.number_of_parameters
        print "numPrograms: %d" % self.number_of_programs
        print "latency: %d" % self.latency

        print "isSynth: %d" % self.is_synth()
        print "receiveEvents: %d" % self.can_receive_events()
        print "receiveTimeInfo: %d" % self.can_receive_timeinfo()
        print "noTail: %d" % self.no_tail()
        
        print "hasEditor: %d" % self.has_editor()

        if show_programs:
            for program_index in range(self.number_of_programs):
                #program_name = self.get_program_name_indexed(program_index)
                self.set_program(program_index)
                program_name = self.get_program_name()
                print "Program %03d: %s" % (program_index, program_name)

        if show_params:
            for param_index in range(self.number_of_parameters):
                param_name = self.get_parameter_name(param_index)
                param_display = self.get_parameter_display(param_index)
                param_label = self.get_parameter_label(param_index)
                value = self.get_parameter(param_index)
                print "Param %03d: %s [%s %s] (normalized = %f)" % (param_index, param_name, param_display, param_label, value)
       
