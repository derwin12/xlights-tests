#!/usr/bin/env python3
"""Generate the minimal reference show used by the render scenarios.

Writes show/xlights_rgbeffects.xml, show/xlights_networks.xml and one
show/<scenario>.xsq per scenario. Effect scenarios are derived from xLights'
resources/effectmetadata/*.json: a defaults segment, one segment per static
choice option, and one segment with every checkbox flipped. Effects that need
a face, state, image, audio or another model, and the feature scenarios
(transitions, layer blending, buffers, colour adjustments, value curves,
timing triggers, submodels) are hand-written below.

Usage: gen_show.py <xlights-source-dir> <out-show-dir>

The output is deterministic; rerun it after changing this file and commit the
result. Regenerating after an xLights metadata change can add segments, which
changes the scenario's fseq and needs a rebaseline.
"""

import json
import math
import struct
import sys
import wave
import zlib
from pathlib import Path
from xml.sax.saxutils import quoteattr, escape

SEGMENT_MS = 1000
FRAME_MS = 50
MAX_SEGMENTS = 50

# Generated into the show so the effects that need media have some. The audio
# is a synthetic beat + sweep, so the repo carries nothing copyrighted.
AUDIO_FILE = "media/beat.wav"
AUDIO_SECONDS = 60
AUDIO_RATE = 16000
IMAGE_FILE = "media/gradient.png"
# A 3 s synthetic test pattern (ffmpeg testsrc2, 64x36, H.264), committed
# rather than generated because the CI container has no ffmpeg binary.
VIDEO_FILE = "media/testsrc.mp4"
SHADER_FILE = "media/pattern.fs"
# Glediator raw frames are sized to the buffer they play on: the Matrix's
# 32x16. The CSV form is size-independent, so it plays on every model.
GLED_FILE = "media/pattern.gled"
GLED_CSV_FILE = "media/pattern.csv"
GLED_SIZE = (32, 16)
GLED_FRAMES = 20

# Effects the generic metadata walk can't drive; each gets a hand-written
# scenario further down.
SKIP_EFFECTS = {
    "DMX", "Duplicate", "Faces", "Glediator", "Guitar", "Moving Head",
    "Music", "Piano", "Pictures", "Servo", "Shader", "Sketch", "State",
    "VU Meter", "Video",
}

# Settings every segment of an effect needs to produce visible output.
BASE_SETTINGS = {
    # The built-in bitmap font renders the same on every OS; OS fonts don't.
    "Text": {"E_TEXTCTRL_Text": "xLights", "E_CHOICE_Text_Font": "7-7x9 Bold"},
}

# Scenario name -> why its render is allowed to differ between runs or from
# its baseline. Shown on the dashboard as an expected failure.
EXPECTED = {
    "Effect_Liquid": "physics simulation (LiquidFun) is not deterministic",
    "Effect_SingleStrandFX_Phased": "WS2812FX::phased_base keeps its phase in a function-level static shared by "
                                    "every model and render thread (FX.cpp), so output depends on thread order",
}

# Single Strand FX modes split out of Effect_SingleStrandFX because they don't
# render the same twice (see EXPECTED).
NONDETERMINISTIC_FX = ["Phased", "Phased Noise"]


# ---------------------------------------------------------------- models

def models():
    """(name, DisplayAs, attrs, node count, x, y)."""
    m = []
    m.append(("Matrix", "Matrix", dict(NumStrings=16, NodesPerString=32, StrandsPerString=1,
              Vertical="false", NoZig="false", AlternateNodes="false", ScaleX=1.6, ScaleY=0.8), 512, -300, 150))
    m.append(("Tree", "Tree", dict(NumStrings=12, NodesPerString=50, StrandsPerString=1, TreeType=0,
              TreeDegrees=360, TreeRotation=3, TreeSpiralRotations=0, TreeBottomTopRatio=6,
              TreePerspective=0.2, StrandDir="Vertical", ScaleX=0.5, ScaleY=0.8), 600, 0, 150))
    m.append(("Arches", "Arches", dict(NumArches=3, NodesPerArch=25, Arc=180, Hollow=70,
              LightsPerNode=1, Height=1.0, X2=150, Y2=0, Z2=0), 75, -300, -50))
    m.append(("Line", "Single Line", dict(NumStrings=1, NodesPerString=50, LightsPerNode=1,
              X2=300, Y2=0, Z2=0), 50, -150, -120))
    m.append(("Star", "Star", dict(NumStrings=1, NodesPerString=40, StarPoints=5, LayerSizes="40",
              starRatio=2.618034, StarStartLocation="Top Ctr-CW", ScaleX=0.4, ScaleY=0.4), 40, 250, 200))
    m.append(("Wreath", "Wreath", dict(NumStrings=1, NodesPerString=40, ScaleX=0.4, ScaleY=0.4), 40, 250, 50))
    m.append(("Icicles", "Icicles", dict(NumStrings=1, NodesPerString=80, DropPattern="3,4,5,4",
              AlternateNodes="false", X2=400, Y2=0, Z2=0), 80, -200, 300))
    m.append(("Window", "Window Frame", dict(TopNodes=20, SideNodes=12, BottomNodes=20,
              Rotation="Clockwise", ScaleX=0.8, ScaleY=0.6), 64, 300, -80))
    m.append(("Sphere", "Sphere", dict(NumStrings=10, NodesPerString=30, StrandsPerString=1,
              Degrees=360, StartLatitude=-75, EndLatitude=75, NoZig="false", AlternateNodes="false",
              ScaleX=0.5, ScaleY=0.5, ScaleZ=0.5), 300, 450, 150))
    m.append(("Cube", "Cube", dict(CubeWidth=6, CubeHeight=6, CubeDepth=6, Strings=1,
              Start="Front Bottom Left", Style="Horizontal Left/Right", StrandPerLine="Zig Zag",
              StrandPerLayer="FALSE", ScaleX=0.5, ScaleY=0.5, ScaleZ=0.5), 216, 450, -50))
    # 7x7 ring drawn as a custom model.
    ring = [(0, 2), (0, 3), (0, 4), (1, 1), (1, 5), (2, 0), (2, 6), (3, 0), (3, 6),
            (4, 0), (4, 6), (5, 1), (5, 5), (6, 2), (6, 3), (6, 4)]
    compressed = ";".join(f"{i + 1},{r},{c},0" for i, (r, c) in enumerate(ring))
    m.append(("Custom", "Custom", dict(CustomWidth=7, CustomHeight=7, Depth=1,
              CustomModelCompressed=compressed, ScaleX=0.4, ScaleY=0.4), len(ring), -450, 50))
    m.append(("Canes", "Candy Canes", dict(NumCanes=3, NodesPerCane=18, LightsPerNode=1,
              CandyCaneHeight=1.0, CandyCaneReverse="false", CandyCaneSticks="false",
              AlternateNodes="false", X2=120, Y2=0, Z2=0, Height=1.0), 54, 150, -150))
    m.append(("Circle", "Circle", dict(NumStrings=1, NodesPerString=60, LayerSizes="30,20,10",
              centerPercent=20, InsideOut="0", ScaleX=0.4, ScaleY=0.4), 60, -450, 250))
    m.append(("Spinner", "Spinner", dict(NumStrings=1, NodesPerArm=10, ArmsPerString=6, Hollow=20,
              StartAngle=0, Arc=360, ZigZag="false", Alternate="false", ScaleX=0.4, ScaleY=0.4), 60, 550, 250))
    m.append(("PolyLine", "Poly Line", dict(NodesPerString=60, NumPoints=4, PolyStrings=1, LightsPerNode=1,
              PointData="0.000000,0.000000,0.000000,0.300000,0.500000,0.000000,0.700000,0.500000,0.000000,1.000000,0.000000,0.000000",
              cPointData="", DropPattern="1", AlternateNodes="false", ModelHeight=1.0,
              ScaleX=200, ScaleY=100, ScaleZ=100), 60, -100, 380))
    return m


def single_line(name, x, y, nodes=20, **attrs):
    a = dict(NumStrings=1, NodesPerString=nodes, LightsPerNode=1, X2=150, Y2=0, Z2=0)
    a.update(attrs)
    return (name, "Single Line", a, nodes, x, y)


def dmx_attrs(channels, **attrs):
    a = dict(StringType="Single Color White", DmxChannelCount=channels, _channels=channels,
             ScaleX=1.0, ScaleY=1.0, ScaleZ=1.0)
    a.update(attrs)
    return a


MH_MOTORS = [
    '<PanMotor ChannelCoarse="1" ChannelFine="2" MinLimit="-180" MaxLimit="180" RangeOfMotion="540.000000" '
    'OrientZero="0" OrientHome="90" SlewLimit="0.000000" SpeedChannel="0" Reverse="0" UpsideDown="0" />',
    '<TiltMotor ChannelCoarse="3" ChannelFine="4" MinLimit="-90" MaxLimit="90" RangeOfMotion="180.000000" '
    'OrientZero="0" OrientHome="90" SlewLimit="0.000000" SpeedChannel="0" Reverse="0" UpsideDown="0" />',
]
MH_RGBW = dict(DmxColorType=0, DmxRedChannel=6, DmxGreenChannel=7, DmxBlueChannel=8, DmxWhiteChannel=9,
               MhDimmerChannel=5, DmxShutterChannel=10, DmxShutterOpen=1, DmxShutterOnValue=255)
MH_WHEEL = dict(DmxColorType=1, DmxColorWheelChannel=6, DmxDimmerChannel=5, MhDimmerChannel=5,
                DmxShutterChannel=10, DmxShutterOpen=1, DmxShutterOnValue=255,
                **{f"DmxColorWheel{k}{i}": v for i, (c, d) in enumerate([("#ffffff", 0), ("#ff0000", 20), ("#00ff00", 40),
                                                                           ("#0000ff", 60), ("#ffff00", 80)])
                   for k, v in (("Color", c), ("DMX", d))})
MOVING_HEADS = ["MH1", "MH2", "MH3", "MH4"]


def extra_models():
    """Models used only by their own scenarios: they stay out of All Models so
    the generic effect scenarios don't change when these are added."""
    m = []
    # DMX fixtures: two advanced and two basic moving heads (RGBW and colour
    # wheel), an RGB floodlight, a general fixture and a two-servo model.
    m.append(("MH1", "DmxMovingHeadAdv", dmx_attrs(12, DmxFixture="MH1", _children=MH_MOTORS, **MH_RGBW), 0, -300, 500))
    m.append(("MH2", "DmxMovingHeadAdv", dmx_attrs(12, DmxFixture="MH2", _children=MH_MOTORS, **MH_RGBW), 0, -150, 500))
    m.append(("MH3", "DmxMovingHead", dmx_attrs(12, DmxFixture="MH3", DmxStyle="Moving Head Top", _children=MH_MOTORS, **MH_WHEEL), 0, 0, 500))
    m.append(("MH4", "DmxMovingHead", dmx_attrs(12, DmxFixture="MH4", DmxStyle="Moving Head Bars", _children=MH_MOTORS, **MH_RGBW), 0, 150, 500))
    m.append(("Flood", "DmxFloodlight", dmx_attrs(4, DmxColorType=0, DmxRedChannel=1, DmxGreenChannel=2, DmxBlueChannel=3, DmxWhiteChannel=4), 0, 300, 500))
    m.append(("DmxGen", "DmxGeneral", dmx_attrs(8, DmxColorType=0, DmxRedChannel=2, DmxGreenChannel=3, DmxBlueChannel=4,
                                                 DmxPresetChannel0=8, DmxPresetValue0=200, DmxPresetDesc0="Strobe"), 0, 450, 500))
    m.append(("Servos", "DmxServo", dmx_attrs(4, NumServos=2, Bits16=1, _children=[
        '<Servo1 Channel="1" MinLimit="1" MaxLimit="65535" RangeOfMotion="180.000000" ServoStyle="Rotate Z" />',
        '<Servo2 Channel="3" MinLimit="1" MaxLimit="65535" RangeOfMotion="180.000000" ServoStyle="Translate Y" />']), 0, 600, 500))

    # Output variations on a 20-node line: node orders, white/single-colour
    # strings, every RGBW handling, brightness and gamma curves.
    y = 650
    for name, st in (("V_GRB", "GRB Nodes"), ("V_BRG", "BRG Nodes"), ("V_RGBWW", "RGBWW Nodes")):
        m.append(single_line(name, -300, y, StringType=st, _channels=20 * (5 if "WW" in st else 3)))
        y += 15
    for i, h in enumerate(["R=G=B -> W", "RGB Only", "White Only", "Advanced", "White On All"]):
        m.append(single_line(f"V_RGBW{i}", -300, y, StringType="RGBW Nodes", RGBWHandling=h, _channels=80))
        y += 15
    # A single-colour line is one dimmer channel per string, not per node.
    for name, st in (("V_White", "Single Color White"), ("V_Red", "Single Color Red"), ("V_Intensity", "Single Color Intensity")):
        m.append(single_line(name, -300, y, nodes=5, NumStrings=4, StringType=st, _channels=4))
        y += 15
    m.append(single_line("V_Bright", -300, y, ModelBrightness=-40))
    y += 15
    m.append(single_line("V_Gamma", -300, y, _children=['<dimmingCurve><all brightness="0" gamma="2.2" /></dimmingCurve>']))
    y += 15
    m.append(single_line("V_RGBCurve", -300, y, _children=[
        '<dimmingCurve><red brightness="-50" gamma="1.0" /><green brightness="0" gamma="1.0" /><blue brightness="0" gamma="2.0" /></dimmingCurve>']))
    y += 15
    # Start-channel forms: controller-relative, chained after another model,
    # and offset from another model's start. Each still lands right after the
    # previous model, so the channel map stays contiguous.
    m.append(single_line("V_ChainA", -300, y, _start="controller"))
    m.append(single_line("V_ChainB", -150, y, _start=">V_ChainA:1"))
    m.append(single_line("V_ChainC", 0, y, _start="@V_ChainB:61"))
    y += 15
    # Individual start channels, strings stored in reverse order.
    m.append(("V_Indiv", "Matrix", dict(NumStrings=4, NodesPerString=10, StrandsPerString=1, Vertical="false",
                                        NoZig="false", AlternateNodes="false", Advanced=1, _indiv=True,
                                        ScaleX=0.5, ScaleY=0.3), 40, 200, y))
    # A rotated matrix for the Per Preview buffer.
    m.append(("V_Rotated", "Matrix", dict(NumStrings=8, NodesPerString=16, StrandsPerString=1, Vertical="false",
                                          NoZig="false", AlternateNodes="false", RotateZ=30, ScaleX=0.8, ScaleY=0.5), 128, 450, y))
    y += 60

    # Model types and layout options the core set doesn't use.
    tree = dict(NumStrings=8, NodesPerString=30, StrandsPerString=1, TreeDegrees=360, TreeRotation=3,
                TreeSpiralRotations=0, TreeBottomTopRatio=6, TreePerspective=0.2, StrandDir="Vertical",
                ScaleX=0.4, ScaleY=0.5)
    m.append(("T_Flat", "Tree", dict(tree, TreeType=1, TreeDegrees=180), 240, -450, y))
    m.append(("T_Ribbon", "Tree", dict(tree, TreeType=2), 240, -300, y))
    m.append(("T_Spiral", "Tree", dict(tree, TreeType=0, TreeSpiralRotations=2.5), 240, -150, y))
    m.append(("M_Vert", "Matrix", dict(NumStrings=8, NodesPerString=20, StrandsPerString=2, Vertical="true",
                                       NoZig="false", AlternateNodes="true", ScaleX=0.5, ScaleY=0.4), 160, 0, y))
    m.append(("M_NoZig", "Matrix", dict(NumStrings=10, NodesPerString=12, StrandsPerString=1, Vertical="false",
                                        NoZig="true", AlternateNodes="false", StartSide="T", Dir="R",
                                        ScaleX=0.5, ScaleY=0.4), 120, 150, y))
    # Two layers, two strings.
    pts = [(r, c, l) for l in (0, 1) for r in range(4) for c in range(4) if (r in (0, 3) or c in (0, 3))]
    compressed = ";".join(f"{i + 1},{r},{c},{l}" for i, (r, c, l) in enumerate(pts))
    m.append(("C_3D", "Custom", dict(CustomWidth=4, CustomHeight=4, Depth=2, CustomStrings=2,
                                     CustomModelCompressed=compressed, ScaleX=0.3, ScaleY=0.3), len(pts), 300, y))
    m.append(("Star2", "Star", dict(NumStrings=1, NodesPerString=48, StarPoints=6, LayerSizes="30,18",
                                    starRatio=2.0, StarStartLocation="Bottom Ctr-CCW", ScaleX=0.4, ScaleY=0.4), 48, 450, y))
    m.append(("Circle2", "Circle", dict(NumStrings=1, NodesPerString=60, LayerSizes="30,20,10",
                                        centerPercent=40, InsideOut="1", ScaleX=0.4, ScaleY=0.4), 60, 600, y))
    y += 120
    m.append(("Window2", "Window Frame", dict(TopNodes=20, SideNodes=12, BottomNodes=20,
                                               Rotation="Counter Clockwise", ScaleX=0.8, ScaleY=0.6), 64, -450, y))
    m.append(("Spinner2", "Spinner", dict(NumStrings=1, NodesPerArm=10, ArmsPerString=6, Hollow=10, StartAngle=45,
                                          Arc=180, ZigZag="true", Alternate="true", ScaleX=0.4, ScaleY=0.4), 60, -300, y))
    m.append(("Icicles2", "Icicles", dict(NumStrings=2, NodesPerString=40, DropPattern="2,6", AlternateNodes="true",
                                          X2=300, Y2=0, Z2=0), 80, -150, y))
    m.append(("Canes2", "Candy Canes", dict(NumCanes=3, NodesPerCane=18, LightsPerNode=1, CandyCaneHeight=0.6,
                                            CandyCaneReverse="true", CandyCaneSticks="true", AlternateNodes="true",
                                            X2=120, Y2=0, Z2=0, Height=1.0), 54, 150, y))
    m.append(("MultiPt", "MultiPoint", dict(NumPoints=6, MultiStrings=1, ModelHeight=1.0,
                                            PointData=",".join(f"{x:.6f},{yy:.6f},0.000000" for x, yy in
                                                               [(0, 0), (0.2, 0.6), (0.4, 0.1), (0.6, 0.9), (0.8, 0.3), (1, 0.7)]),
                                            ScaleX=200, ScaleY=100, ScaleZ=100), 6, 300, y))
    m.append(("ChanBlock", "Channel Block", dict(NumChannels=8, X2=100, Y2=0, Z2=0, **{
        f"ChannelProperties.ChannelColor{i + 1}": c for i, c in enumerate(
            ["red", "green", "blue", "white", "yellow", "cyan", "magenta", "orange"])}), 8, 450, y))
    m.append(("ImageM", "Image", dict(Image=IMAGE_FILE, WhiteAsAlpha="False", OffBrightness=60,
                                      StringType="Single Color Intensity", _channels=1), 1, 600, y))
    m.append(("LabelM", "Label", dict(LabelText="xlights-tests", LabelFontSize=12, LabelTextColor="#FFFF00"), 1, 650, y))
    y += 120

    # A matrix carrying every submodel form: sub-buffer, Keep XY and Stacked
    # Strands range styles, reversed ranges and a node list.
    m.append(("SM_Matrix", "Matrix", dict(NumStrings=16, NodesPerString=16, StrandsPerString=1, Vertical="false",
                                          NoZig="false", AlternateNodes="false", ScaleX=0.6, ScaleY=0.6, _children=[
        '<subModel name="Window" layout="horizontal" type="subbuffer" bufferstyle="Default" subBuffer="20x20x80x70" />',
        '<subModel name="XY" layout="horizontal" type="ranges" bufferstyle="Keep XY" '
        'line0="1-16" line1="40-48" line2="120-136" line3="250-256" />',
        '<subModel name="Stacked" layout="horizontal" type="ranges" bufferstyle="Stacked Strands" '
        'line0="1-16" line1="33-48" line2="65-80" />',
        '<subModel name="Reversed" layout="vertical" type="ranges" bufferstyle="Default" '
        'line0="32-17" line1="64-49" line2="96-81" />',
        '<subModel name="Dots" layout="horizontal" type="ranges" bufferstyle="Default" '
        'line0="1,5,9,13,100,104,108,112" line1="200,,210,,220" />',
    ]), 256, -300, y))

    # DMX fixtures with their own servo channel layouts.
    m.append(("Skull", "DmxSkull", dmx_attrs(26, DmxColorType=0, DmxRedChannel=16, DmxGreenChannel=17, DmxBlueChannel=18,
                                              DmxEyeBrtChannel=15), 0, 0, y))
    m.append(("Servo3D", "DmxServo3d", dmx_attrs(4, NumServos=2, NumStatic=1, NumMotion=2, Bits16=1, _children=[
        '<Servo1 Channel="1" MinLimit="1" MaxLimit="65535" RangeOfMotion="180.000000" ServoStyle="Rotate X" />',
        '<Servo2 Channel="3" MinLimit="1" MaxLimit="65535" RangeOfMotion="90.000000" ServoStyle="Rotate Y" />']), 0, 150, y))
    return m


NEW_TYPES = ["T_Flat", "T_Ribbon", "T_Spiral", "M_Vert", "M_NoZig", "C_3D", "Star2", "Circle2", "Window2",
             "Spinner2", "Icicles2", "Canes2", "MultiPt", "ChanBlock", "ImageM", "LabelM"]
NEW_TYPES_GROUP = "New Types"


VARIANTS = ["V_GRB", "V_BRG", "V_RGBWW"] + [f"V_RGBW{i}" for i in range(5)] + [
    "V_White", "V_Red", "V_Intensity", "V_Bright", "V_Gamma", "V_RGBCurve",
    "V_ChainA", "V_ChainB", "V_ChainC", "V_Indiv", "V_Rotated"]

GROUP = "All Models"
MIXED_GROUP = "Mixed Group"
MH_GROUP = "Moving Heads"

# Child elements of a model: submodels, a node-range face and a node-range
# state definition, so Faces, State and submodel buffers have something to use.
FACE = "Singer"
STATE = "Points"
CHILDREN = {
    "Matrix": [
        '<subModel name="Top" layout="horizontal" type="ranges" bufferstyle="Default" '
        'line0="385-416" line1="417-448" line2="449-480" line3="481-512" />',
        '<subModel name="Columns" layout="vertical" type="ranges" bufferstyle="Default" '
        'line0="1-32" line1="97-128" line2="193-224" line3="289-320" line4="385-416" line5="481-512" />',
        '<faceInfo Name="Singer" Type="NodeRange" CustomColors="0" '
        'FaceOutline="1-32,481-512" Eyes-Open="105-108,121-124" Eyes-Closed="137-140,153-156" '
        'Mouth-AI="230-235,262-267,294-299" Mouth-E="262-267,294-299" Mouth-etc="262-267" '
        'Mouth-FV="294-299" Mouth-L="230-235,294-299" Mouth-MBP="262-267" Mouth-O="229-236,261,268,293-300" '
        'Mouth-rest="263-266" Mouth-U="263-266,295-298" Mouth-WQ="264-265,296-297" />',
    ],
    "Tree": [
        '<subModel name="Bottom" layout="horizontal" type="ranges" bufferstyle="Default" '
        + " ".join(f'line{i}="{i * 50 + 1}-{i * 50 + 15}"' for i in range(12)) + ' />',
    ],
    "Star": [
        '<stateInfo Name="Points" Type="NodeRange" CustomColors="1" '
        's001="1-8" s001-Name="one" s001-Color="#ff0000" '
        's002="9-16" s002-Name="two" s002-Color="#00ff00" '
        's003="17-24" s003-Name="three" s003-Color="#0000ff" '
        's004="25-32" s004-Name="four" s004-Color="#ffff00" '
        's005="33-40" s005-Name="five" s005-Color="#ffffff" />',
    ],
}


def write_rgbeffects(path, model_list, group_names):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<xrgb>", '  <models type="rgb_effects">']
    ch = 1
    for name, display, attrs, nodes, x, y in model_list:
        a = dict(name=name, DisplayAs=display, StringType="RGB Nodes", StartChannel=ch,
                 StartSide="B", Dir="L", Antialias=1, PixelSize=2, Transparency=0,
                 LayoutGroup="Default", versionNumber=8, WorldPosX=x, WorldPosY=y, WorldPosZ=0)
        a.update(attrs)
        kids = list(CHILDREN.get(name, [])) + list(a.pop("_children", []))
        chans = a.pop("_channels", nodes * 3)
        start = a.pop("_start", None)
        if start == "controller":
            a["StartChannel"] = f"!Test Controller:{ch}"
        elif start:
            a["StartChannel"] = start
        if a.pop("_indiv", False):
            per = chans // a["NumStrings"]
            for i in range(a["NumStrings"]):
                a[f"String{i + 1}"] = str(ch + (a["NumStrings"] - 1 - i) * per)
        open_tag = "    <model " + " ".join(f"{k}={quoteattr(str(v))}" for k, v in a.items())
        if kids:
            lines.append(open_tag + ">")
            lines += ["      " + k for k in kids]
            lines.append("    </model>")
        else:
            lines.append(open_tag + " />")
        ch += chans
    lines.append("  </models>")
    lines.append('  <modelGroups type="rgb_effects">')
    names = ",".join(group_names)
    lines.append(f'    <modelGroup name={quoteattr(GROUP)} DisplayAs="ModelGroup" DefaultCamera="2D" '
                 f'GridSize="400" layout="minimalGrid" LayoutGroup="Default" models={quoteattr(names)} />')
    lines.append(f'    <modelGroup name={quoteattr(MIXED_GROUP)} DisplayAs="ModelGroup" DefaultCamera="2D" '
                 f'GridSize="400" layout="minimalGrid" LayoutGroup="Default" '
                 f'models="Matrix/Top,Tree/Bottom,Star,Circle,Spinner" />')
    lines.append(f'    <modelGroup name={quoteattr(MH_GROUP)} DisplayAs="ModelGroup" DefaultCamera="2D" '
                 f'GridSize="400" layout="minimalGrid" LayoutGroup="Default" models={quoteattr(",".join(MOVING_HEADS))} />')
    lines.append(f'    <modelGroup name={quoteattr(NEW_TYPES_GROUP)} DisplayAs="ModelGroup" DefaultCamera="2D" '
                 f'GridSize="400" layout="minimalGrid" LayoutGroup="Default" models={quoteattr(",".join(NEW_TYPES))} />')
    lines.append("  </modelGroups>")
    lines.append("  <view_objects />")
    lines.append("  <layoutGroups />")
    lines.append("  <perspectives />")
    lines.append("  <settings />")
    lines.append("</xrgb>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ch - 1


def write_networks(path, channels):
    path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Networks computer="xlights-tests">
  <Controller Id="1" Name="Test Controller" Description="" Type="Ethernet" Vendor="" Model="" Variant="" AutoSize="0" ActiveState="Active" AutoLayout="0" AutoUpload="0" SuppressDuplicates="0" Monitor="0" IP="127.0.0.1" Protocol="DDP" Priority="100" Version="1">
    <network ChannelsPerPacket="1440" KeepChannelNumbers="1" ComPort="127.0.0.1" BaudRate="1" NetworkType="DDP" MaxChannels="{channels}" Enabled="Yes" />
  </Controller>
</Networks>
""", encoding="utf-8")


# ------------------------------------------------------------- sequences

PALETTE = ("C_BUTTON_Palette1=#FF0000,C_BUTTON_Palette2=#00FF00,C_BUTTON_Palette3=#0000FF,"
           "C_BUTTON_Palette4=#FFFF00,C_BUTTON_Palette5=#FFFFFF,C_BUTTON_Palette6=#000000,"
           "C_BUTTON_Palette7=#00FFFF,C_BUTTON_Palette8=#FF00FF,"
           "C_CHECKBOX_Palette1=1,C_CHECKBOX_Palette2=1,C_CHECKBOX_Palette3=1")


class Sequence:
    """Collects (element, layer, effect name, settings, start, end) placements."""

    def __init__(self, media=None, frame_ms=FRAME_MS, model_blending=True, palette=PALETTE):
        self.placements = []
        self.end_ms = 0
        self.media = media
        self.frame_ms = frame_ms
        self.model_blending = model_blending
        self.palette = palette
        self.timing = {}  # name -> list of layers, each a list of (label, start, end)

    def add_timing(self, name, *layers):
        self.timing[name] = [list(l) for l in layers]

    def add(self, element, layer, effect, settings, start, end, palette=None):
        """palette replaces the sequence palette for this one effect; colours
        in an effect's settings are ignored, xLights reads them from here."""
        self.placements.append((element, layer, effect, settings, start, end, palette or self.palette))
        self.end_ms = max(self.end_ms, end)

    def write(self, path, element_names):
        # Elements the scenario uses beyond the standard list (DMX fixtures,
        # output variants) are appended so they get rows too.
        element_names = list(element_names)
        for element, *_ in self.placements:
            top = element.split("/", 1)[0]
            if top in element_names:
                continue
            element_names.append(top)
        db = []
        db_index = {}
        per_element = {e: {} for e in element_names}
        per_sub = {e: {} for e in element_names}
        palettes = [self.palette]
        for element, layer, effect, settings, start, end, palette in self.placements:
            key = ",".join(f"{k}={v}" for k, v in sorted(settings.items()))
            if key not in db_index:
                db_index[key] = len(db)
                db.append(key)
            if palette not in palettes:
                palettes.append(palette)
            item = (effect, db_index[key], start, end, palettes.index(palette))
            if "/" in element:
                parent, sub = element.split("/", 1)
                per_sub[parent].setdefault(sub, []).append(item)
            else:
                per_element[element].setdefault(layer, []).append(item)

        duration = (self.end_ms + 500) / 1000.0
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               f'<xsequence BaseChannel="0" ChanCtrlBasic="0" ChanCtrlColor="0" FixedPointTiming="1" ModelBlending="{str(self.model_blending).lower()}">',
               "  <head>",
               "    <version>2026.1</version>",
               "    <author>xlights-tests</author>",
               f"    <sequenceTiming>{self.frame_ms} ms</sequenceTiming>",
               f"    <sequenceType>{'Media' if self.media else 'Animation'}</sequenceType>",
               f"    <mediaFile>{escape(self.media or '')}</mediaFile>",
               f"    <sequenceDuration>{duration:.3f}</sequenceDuration>",
               "  </head>",
               "  <ColorPalettes>",
               *[f"    <ColorPalette>{pal}</ColorPalette>" for pal in palettes],
               "  </ColorPalettes>",
               "  <EffectDB>"]
        out += [f"    <Effect>{escape(s)}</Effect>" for s in db]
        out += ["  </EffectDB>", "  <DisplayElements>"]
        out += [f'    <Element collapsed="false" type="timing" name={quoteattr(t)} visible="true" active="false" />' for t in self.timing]
        out += [f'    <Element collapsed="false" type="model" name={quoteattr(e)} visible="true" />' for e in element_names]
        out += ["  </DisplayElements>", "  <ElementEffects>"]
        for t, layers in self.timing.items():
            out.append(f'    <Element type="timing" name={quoteattr(t)}>')
            for layer in layers:
                out.append("      <EffectLayer>")
                out += [f'        <Effect label={quoteattr(lbl)} startTime="{a}" endTime="{b}" />' for lbl, a, b in layer]
                out.append("      </EffectLayer>")
            out.append("    </Element>")
        for e in element_names:
            out.append(f'    <Element type="model" name={quoteattr(e)}>')
            layers = per_element[e]
            for layer in range(max(layers.keys(), default=0) + 1):
                out.append("      <EffectLayer>")
                for effect, ref, start, end, pi in sorted(layers.get(layer, []), key=lambda p: p[2]):
                    out.append(f'        <Effect ref="{ref}" name={quoteattr(effect)} startTime="{start}" endTime="{end}" palette="{pi}" />')
                out.append("      </EffectLayer>")
            for sub, effs in per_sub[e].items():
                out.append(f'      <SubModelEffectLayer name={quoteattr(sub)}>')
                for effect, ref, start, end, pi in sorted(effs, key=lambda p: p[2]):
                    out.append(f'        <Effect ref="{ref}" name={quoteattr(effect)} startTime="{start}" endTime="{end}" palette="{pi}" />')
                out.append("      </SubModelEffectLayer>")
            out.append("    </Element>")
        out += ["  </ElementEffects>", "  <lastView>0</lastView>", "</xsequence>"]
        path.write_text("\n".join(out) + "\n", encoding="utf-8")


def effect_segments(meta):
    """Settings dicts: defaults, each non-default static choice option, all checkboxes flipped."""
    segs = [{}]
    flipped = {}
    for p in meta["properties"]:
        if p.get("platform") or p.get("dynamicOptions"):
            continue
        ct = p.get("controlType")
        if ct == "choice" and p.get("options"):
            for opt in p["options"]:
                if opt != p.get("default"):
                    segs.append({f"E_CHOICE_{p['id']}": opt})
        elif ct == "checkbox":
            default = p.get("default")
            on = default in (True, 1, "1", "true", "True")
            flipped[f"E_CHECKBOX_{p['id']}"] = "0" if on else "1"
    if flipped:
        segs.append(flipped)
    return segs[:MAX_SEGMENTS]


def place_segments(seq, models_, effect, segs, canvas=False, base=None):
    """Each segment on every model, then the defaults once more on the group.

    A canvas-mode effect (Kaleidoscope, Warp) only transforms the layers below
    it, so it gets Bars on layer 1 to work on.
    """
    base = dict(BASE_SETTINGS.get(effect, {}), **(base or {}))
    if canvas:
        base["T_CHECKBOX_Canvas"] = "1"
    t = 0
    for s in segs:
        for name in models_:
            seq.add(name, 0, effect, dict(base, **s), t, t + SEGMENT_MS)
        t += SEGMENT_MS
    seq.add(GROUP, 0, effect, dict(base, **segs[0]), t, t + SEGMENT_MS)
    seq.add(GROUP, 0, effect, dict(base, **segs[0], **{"B_CHOICE_BufferStyle": "Per Preview"}), t + SEGMENT_MS, t + 2 * SEGMENT_MS)
    if canvas:
        for name in models_:
            seq.add(name, 1, "Bars", {"E_CHOICE_Bars_Direction": "Left"}, 0, t + 2 * SEGMENT_MS)


def feature_sequences(model_names):
    feats = {}

    # In/out transitions, CPU and GPU kinds.
    s = Sequence()
    kinds = ["Fade", "Wipe", "Clock", "From Middle", "Square Explode", "Circle Explode", "Blinds",
             "Blend", "Slide Checks", "Slide Bars", "Shatter", "Star", "Pinwheel", "Bow Tie",
             "Blobs", "Fold", "Zoom", "Circular Swirl", "Doorway", "Swap", "Circles", "Dissolve"]
    t = 0
    for k in kinds:
        st = {"T_CHOICE_In_Transition_Type": k, "T_TEXTCTRL_Fadein": "0.4",
              "T_CHOICE_Out_Transition_Type": k, "T_TEXTCTRL_Fadeout": "0.4"}
        for m in model_names:
            s.add(m, 0, "Bars", st, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    feats["Feature_Transitions"] = s

    # Two-layer blending with every mix method.
    s = Sequence()
    methods = ["Normal", "Effect 1", "Effect 2", "1 is Mask", "2 is Mask", "1 is Unmask", "2 is Unmask",
               "1 is True Unmask", "2 is True Unmask", "1 reveals 2", "2 reveals 1", "Shadow 1 on 2",
               "Shadow 2 on 1", "Layered", "Highlight", "Highlight Vibrant", "Additive", "Subtractive",
               "Brightness", "Average", "Bottom-Top", "Left-Right", "Max", "Min"]
    t = 0
    for meth in methods:
        for m in model_names:
            s.add(m, 0, "Butterfly", {"T_CHOICE_LayerMethod": meth, "T_SLIDER_EffectLayerMix": "50"}, t, t + SEGMENT_MS)
            s.add(m, 1, "Bars", {"E_CHOICE_Bars_Direction": "Left"}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    feats["Feature_LayerBlend"] = s

    # Group buffer styles.
    s = Sequence()
    styles = ["Default", "Per Preview", "Single Line", "As Pixel", "Horizontal Per Model", "Vertical Per Model",
              "Horizontal Per Model/Strand", "Vertical Per Model/Strand", "Single Line Model As A Pixel",
              "Default Model As A Pixel", "Overlay - Centered", "Overlay - Scaled",
              "Horizontal Stack", "Vertical Stack", "Horizontal Stack - Scaled", "Vertical Stack - Scaled",
              "Per Model Default", "Per Model Per Preview", "Per Model Single Line", "Per Model Default Deep",
              "Per Model Vertical Per Strand", "Per Model Horizontal Per Strand"]
    t = 0
    for st in styles:
        s.add(GROUP, 0, "Spirals", {"B_CHOICE_BufferStyle": st}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    feats["Feature_GroupBuffers"] = s

    # Buffer transforms, blur, sub-buffer, rotozoom.
    s = Sequence()
    variants = [{"B_CHOICE_BufferTransform": x} for x in
                ["Rotate CC 90", "Rotate CW 90", "Rotate 180", "Flip Vertical", "Flip Horizontal",
                 "Rotate CC 90 Flip Horizontal", "Rotate CW 90 Flip Horizontal"]]
    variants += [{"B_SLIDER_Blur": "8"},
                 {"B_CUSTOM_SubBuffer": "10.00x10.00x60.00x80.00x0.00x0.00"},
                 {"B_SLIDER_Rotation": "30", "B_SLIDER_Zoom": "15"},
                 {"B_VALUECURVE_Rotation": "Active=TRUE|Id=ID_VALUECURVE_Rotation|Type=Ramp|Min=0.00|Max=100.00|P1=0.00|P2=100.00|RV=TRUE|"},
                 {"B_SLIDER_XRotation": "45", "B_SLIDER_YRotation": "30"},
                 {"B_CHECKBOX_OverlayBkg": "1"}]
    t = 0
    for v in variants:
        for m in model_names:
            s.add(m, 0, "Bars", v, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    feats["Feature_BufferTransforms"] = s

    # Colour adjustments.
    s = Sequence()
    variants = [{"C_SLIDER_Brightness": "40"}, {"C_SLIDER_Brightness": "250"}, {"C_SLIDER_Contrast": "60"},
                {"C_SLIDER_Color_HueAdjust": "50"}, {"C_SLIDER_Color_SaturationAdjust": "-60"},
                {"C_SLIDER_Color_ValueAdjust": "-40"}, {"C_SLIDER_SparkleFrequency": "100"},
                {"C_VALUECURVE_Brightness": "Active=TRUE|Id=ID_VALUECURVE_Brightness|Type=Sine|Min=0.00|Max=400.00|P1=0.00|P2=100.00|P3=50.00|P4=50.00|RV=TRUE|"}]
    t = 0
    for v in variants:
        for m in model_names:
            s.add(m, 0, "Color Wash", v, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    feats["Feature_ColorAdjust"] = s

    # Value curve shapes on an effect parameter.
    s = Sequence()
    shapes = ["Ramp", "Ramp Up/Down", "Ramp Up/Down Hold", "Saw Tooth", "Square", "Parabolic Down",
              "Parabolic Up", "Logarithmic Up", "Logarithmic Down", "Exponential Up", "Exponential Down",
              "Sine", "Abs Sine", "Decaying Sine", "Flat", "Random"]
    t = 0
    for sh in shapes:
        vc = f"Active=TRUE|Id=ID_VALUECURVE_Bars_Cycles|Type={sh}|Min=0.00|Max=300.00|P1=10.00|P2=200.00|P3=50.00|P4=30.00|RV=TRUE|"
        for m in model_names:
            s.add(m, 0, "Bars", {"E_VALUECURVE_Bars_Cycles": vc}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    feats["Feature_ValueCurves"] = s

    # Effects that fire on timing marks instead of running freely.
    s = Sequence()
    triggers = [
        ("Ripple", {"E_CHOICE_Ripple_TimingTrack": "Beats"}),
        ("Shockwave", {"E_CHOICE_Shockwave_TimingTrack": "Beats"}),
        ("Fireworks", {"E_CHECKBOX_FIRETIMING": "1", "E_CHOICE_FIRETIMINGTRACK": "Beats"}),
        ("Shape", {"E_CHECKBOX_Shape_FireTiming": "1", "E_CHOICE_Shape_FireTimingTrack": "Beats"}),
    ]
    t = 0
    for effect, st in triggers:
        for m in model_names:
            s.add(m, 0, effect, st, t, t + 3 * SEGMENT_MS)
        t += 3 * SEGMENT_MS
    s.add_timing("Beats", beat_marks(t))
    feats["Feature_TimingTriggers"] = s

    # Submodel layers and a group mixing submodels with whole models.
    s = Sequence()
    t = 0
    for sub in ("Matrix/Top", "Matrix/Columns", "Tree/Bottom"):
        s.add(sub, 0, "Bars", {"E_CHOICE_Bars_Direction": "Left"}, t, t + SEGMENT_MS)
        s.add(sub, 0, "Spirals", {}, t + SEGMENT_MS, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    s.add("Matrix", 0, "Color Wash", {}, 0, t)
    for st in ("Default", "Per Preview", "Horizontal Per Model", "Per Model Default", "Overlay - Scaled", "Single Line"):
        s.add(MIXED_GROUP, 0, "Spirals", {"B_CHOICE_BufferStyle": st}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    feats["Feature_SubModels"] = s

    return feats


# --------------------------------------------- effects needing extra input

def beat_marks(end_ms, step=500):
    return [("", a, min(a + step, end_ms)) for a in range(0, end_ms, step)]


PHONEMES = ["AI", "E", "etc", "FV", "L", "MBP", "O", "U", "WQ", "rest"]


def lyric_layers(end_ms):
    """Phrase, word and phoneme layers, one word per second, one phoneme per 250ms."""
    phrases = [("la la la", 0, end_ms)]
    words = [("la", a, a + 1000) for a in range(0, end_ms, 1000)]
    phon = [(PHONEMES[i % len(PHONEMES)], a, a + 250) for i, a in enumerate(range(0, end_ms, 250))]
    return phrases, words, phon


def input_scenarios(src, model_names):
    """Faces, State, Pictures, VU Meter, Music and Duplicate."""
    meta = {}
    for f in (src / "resources" / "effectmetadata").glob("*.json"):
        if not f.name.startswith("_"):
            d = json.loads(f.read_text(encoding="utf-8"))
            meta[d.get("effectName")] = d
    choices = lambda effect, pid: [o for p in meta[effect]["properties"] if p["id"] == pid for o in p.get("options", [])]
    out = {}

    # Faces on the Matrix's node-range face: each phoneme held, then driven by
    # a lyric track with each eye mode, then the built-in matrix face.
    s = Sequence()
    face = {"E_CHOICE_Faces_FaceDefinition": FACE}
    segs = [dict(face, E_CHOICE_Faces_Phoneme=p) for p in PHONEMES]
    segs += [dict(face, E_CHOICE_Faces_TimingTrack="Lyrics", E_CHOICE_Faces_Eyes=e) for e in choices("Faces", "Faces_Eyes")]
    segs += [dict(face, E_CHOICE_Faces_TimingTrack="Lyrics", E_CHECKBOX_Faces_Outline="1", E_CHECKBOX_Faces_Fade="1")]
    segs += [{"E_CHOICE_Faces_FaceDefinition": "Default", "E_CHOICE_Faces_TimingTrack": "Lyrics"}]
    t = 0
    for st in segs:
        s.add("Matrix", 0, "Faces", st, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    s.add_timing("Lyrics", *lyric_layers(t))
    out["Effect_Faces"] = s

    # State on the Star's node-range states: each state by name, then a
    # timing track naming them, through each mode and colour option.
    s = Sequence()
    base = {"E_CHOICE_State_StateDefinition": STATE}
    segs = [dict(base, E_CHOICE_State_State=n) for n in ("one", "two", "three", "four", "five")]
    segs += [dict(base, E_CHOICE_State_TimingTrack="States", E_CHOICE_State_Mode=m) for m in choices("State", "State_Mode")]
    segs += [dict(base, E_CHOICE_State_TimingTrack="States", E_CHOICE_State_Color=c) for c in choices("State", "State_Color")]
    t = 0
    for st in segs:
        s.add("Star", 0, "State", st, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    names = ["one", "two", "three", "four", "five"]
    s.add_timing("States", [(names[i % 5], a, a + 500) for i, a in enumerate(range(0, t, 500))])
    out["Effect_State"] = s

    # Pictures with a generated image, through the metadata segments.
    s = Sequence()
    place_segments(s, model_names, "Pictures", effect_segments(meta["Pictures"]),
                   base={"E_TEXTCTRL_Pictures_Filename": IMAGE_FILE})
    out["Effect_Pictures"] = s

    # Audio-driven effects over the generated beat. VU Meter's shapes only
    # apply to a few types, so it walks the types alone.
    s = Sequence(media=AUDIO_FILE)
    vu = [{}] + [{"E_CHOICE_VUMeter_Type": v} for v in choices("VU Meter", "VUMeter_Type") if v != "Waveform"]
    place_segments(s, model_names, "VU Meter", vu[:MAX_SEGMENTS], base={"E_CHOICE_VUMeter_TimingTrack": "Beats"})
    s.add_timing("Beats", beat_marks(s.end_ms))
    out["Effect_VUMeter"] = s

    s = Sequence(media=AUDIO_FILE)
    # Registered as "Music Effect"; only the metadata calls it "Music".
    place_segments(s, model_names, "Music Effect", effect_segments(meta["Music"]))
    out["Effect_Music"] = s

    # Duplicate copying the Matrix's layer onto every other model, with each
    # override in turn.
    s = Sequence()
    base = {"E_CHOICE_Duplicate_Model": "Matrix", "E_SPINCTRL_Duplicate_Layer": "1"}
    segs = [{}] + [{k: "1"} for k in ("E_CHECKBOX_Duplicate_Override_Palette", "E_CHECKBOX_Duplicate_Override_Color",
                                      "E_CHECKBOX_Duplicate_Override_Timing", "E_CHECKBOX_Duplicate_Override_Buffer")]
    t = 0
    for st in segs:
        for m in model_names:
            if m != "Matrix":
                s.add(m, 0, "Duplicate", dict(base, **st), t, t + SEGMENT_MS)
        t += SEGMENT_MS
    s.add("Matrix", 0, "Bars", {"E_CHOICE_Bars_Direction": "Left"}, 0, t)
    out["Effect_Duplicate"] = s
    return out


def mh_settings(**cmds):
    """One fixture's Moving Head command string. Commas inside a setting value
    are stored as &comma; and the path's semicolons as @."""
    parts = []
    for k, v in cmds.items():
        k = k.replace("_", " ")
        parts.append(f"{k}: {v}" if v is not None else f"{k}: 1")
    return ";".join(parts).replace(",", "&comma;")


def dmx_scenarios():
    out = {}
    heads = ",".join(str(i + 1) for i in range(len(MOVING_HEADS)))

    # Moving Head on the group: positions, offsets and groupings, every
    # pattern, value-curved pan/tilt, a path, colour, wheel, dimmer and
    # shutter; then the same on one fixture on its own.
    ramp = lambda vid, lo, hi: f"Active=TRUE|Id=ID_VALUECURVE_{vid}|Type=Ramp|Min={lo}|Max={hi}|P1=0.00|P2=100.00|RV=TRUE|"
    color = "0.000000,1.000000,1.000000,0.333333,1.000000,1.000000"
    segs = [
        dict(Pan="45.0", Tilt="20.0", Heads=heads, Color=color),
        dict(Pan="0.0", Tilt="0.0", PanOffset="30.0", TiltOffset="10.0", Groupings="2", Heads=heads, Color=color),
        dict(**{"Pan_VC": ramp("MHPan", -180, 180), "Tilt_VC": ramp("MHTilt", -90, 90)}, Heads=heads, Color=color),
        dict(Path="0.3,0.3@C0.5,0.1,0.7,0.3,0.7,0.5@L0.3,0.7@", PathScale="1.0", Heads=heads, Color=color),
        dict(Pan="10.0", Tilt="10.0", Heads=heads, Wheel="0.000000,1.000000,1.000000,0.666667,1.000000,1.000000"),
        dict(Pan="10.0", Tilt="10.0", Heads=heads, Color=color, Dimmer="0.0,0.0,0.5,1.0,1.0,0.0", Shutter="On"),
        dict(Pan="10.0", Tilt="10.0", Heads=heads, Color=color, AutoShutter="1"),
    ]
    for pat in ("Circle", "Eight", "Line", "Line2", "Diamond", "Square", "SquareChoppy", "SquareTrue", "Leaf", "Lissajous"):
        segs.append(dict(Pattern=pat, PatternWidth="90", PatternHeight="45", Cycles="2", Heads=heads, Color=color))
    s = Sequence()
    t = 0
    for seg in segs:
        st = {f"E_TEXTCTRL_MH{i + 1}_Settings": mh_settings(**dict(seg)) for i in range(len(MOVING_HEADS))}
        st["B_CHOICE_BufferStyle"] = "Per Model Default"
        s.add(MH_GROUP, 0, "Moving Head", st, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    for seg in segs[:3]:
        s.add("MH1", 0, "Moving Head", {"E_TEXTCTRL_MH1_Settings": mh_settings(**dict(seg, Heads="1"))}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    out["Effect_MovingHead"] = s

    # DMX channel levels: fixed values, value-curved ramps, inverted.
    s = Sequence()
    segs = [{f"E_SLIDER_DMX{c}": str(32 * c % 256) for c in range(1, 9)},
            {f"E_VALUECURVE_DMX{c}": ramp(f"DMX{c}", 0, 255) for c in range(1, 9)},
            dict({f"E_SLIDER_DMX{c}": "200" for c in range(1, 9)}, **{f"E_CHECKBOX_INVDMX{c}": "1" for c in (1, 3, 5)})]
    t = 0
    for seg in segs:
        for m in ("Flood", "DmxGen"):
            s.add(m, 0, "DMX", seg, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    # Colour effects on the RGB fixtures go through the colour ability.
    for effect in ("On", "Color Wash"):
        for m in ("Flood", "DmxGen"):
            s.add(m, 0, effect, {}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    out["Effect_DMX"] = s

    # Servo: start/end positions on each servo, a value curve, 8-bit output.
    s = Sequence()
    segs = [{"E_CHOICE_Channel": "Servo1", "E_TEXTCTRL_Servo": "10", "E_TEXTCTRL_EndValue": "90"},
            {"E_CHOICE_Channel": "Servo2", "E_TEXTCTRL_Servo": "80", "E_TEXTCTRL_EndValue": "20"},
            {"E_CHOICE_Channel": "Servo1", "E_VALUECURVE_Servo": ramp("Servo", 0, 1000)},
            {"E_CHOICE_Channel": "Servo2", "E_TEXTCTRL_Servo": "50", "E_TEXTCTRL_EndValue": "50", "E_CHECKBOX_16bit": "0"}]
    t = 0
    for seg in segs:
        s.add("Servos", 0, "Servo", seg, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    out["Effect_Servo"] = s
    return out


def sketch_def(*paths):
    """Sketch paths are '|'-separated, their segments ';'-separated; the commas
    inside points are stored as &comma; like any other setting value."""
    return "|".join(paths).replace(",", "&comma;")


def music_scenarios(core_names):
    """Piano and Guitar read notes from timing-track labels; Sketch draws
    paths; Glediator plays raw and CSV frame files; Shader runs an ISF file."""
    out = {}

    # Notes as names, sharps/flats, MIDI numbers, chords and rests.
    note_labels = ["C4", "E4 G4", "C#4", "Bb3", "60,64,67", "F4:A4:C5", "", "G3 B3 D4 F4", "C5", "A4"]
    notes = [(lbl, a, a + 250) for a, lbl in zip(range(0, 60000, 250), note_labels * 24) if lbl]

    s = Sequence()
    base = {"E_CHOICE_Piano_MIDITrack_APPLYLAST": "Notes"}
    segs = [{}, {"E_CHOICE_Piano_Type": "Bars"}, {"E_CHECKBOX_Piano_ShowSharps": "0"},
            {"E_CHECKBOX_Piano_FadeNotes": "1"}, {"E_CHOICE_Piano_Type": "Bars", "E_CHECKBOX_Piano_FadeNotes": "1"},
            {"E_SPINCTRL_Piano_StartMIDI": "48", "E_SPINCTRL_Piano_EndMIDI": "84"},
            {"E_SPINCTRL_Piano_StartMIDI": "55", "E_SPINCTRL_Piano_EndMIDI": "65"},
            {"E_SLIDER_Piano_Scale": "60", "E_SLIDER_Piano_XOffset": "20"},
            {"E_SLIDER_Piano_XOffset": "-30"}]
    t = 0
    for st in segs:
        for m in core_names:
            s.add(m, 0, "Piano", dict(base, **st), t, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    s.add_timing("Notes", [n for n in notes if n[2] <= t])
    out["Effect_Piano"] = s

    # Guitar: chord names, single notes, MIDI numbers and string/fret pairs.
    chord_labels = ["CA", "CG", "CE", "CD", "E2", "A2 D3", "S1P3 S2P5", "40", "S6P0 S5P2 S4P2", "CC"]
    chords = [(lbl, a, a + 400) for a, lbl in zip(range(0, 60000, 400), chord_labels * 15)]
    s = Sequence()
    base = {"E_CHOICE_Guitar_MIDITrack_APPLYLAST": "Chords"}
    segs = [{"E_CHOICE_Guitar_Type": ty} for ty in ("Guitar", "Bass Guitar", "Banjo", "Violin")]
    segs += [{"E_CHOICE_StringAppearance": "Wave"},
             {"E_CHOICE_StringAppearance": "Wave", "E_TEXTCTRL_StringWaveFactor": "2.5", "E_TEXTCTRL_BaseWaveFactor": "3.0",
              "E_CHECKBOX_VaryWaveLengthOnFret": "0"},
             {"E_CHECKBOX_ShowStrings": "1", "E_CHECKBOX_Fade": "1"},
             {"E_CHECKBOX_Collapse": "1", "E_SLIDER_MaxFrets": "8"}]
    t = 0
    for st in segs:
        for m in core_names:
            s.add(m, 0, "Guitar", dict(base, **st), t, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    s.add_timing("Chords", [c for c in chords if c[2] <= t])
    out["Effect_Guitar"] = s

    # Sketch: lines, quadratic and cubic curves, a closed path and several
    # paths, at different draw percentages, thicknesses and motion.
    zigzag = sketch_def("0.1,0.1;L0.3,0.9;L0.5,0.1;L0.7,0.9;L0.9,0.1")
    curves = sketch_def("0.1,0.5;Q0.3,0.0,0.5,0.5;C0.6,1.0,0.8,0.0,0.9,0.5")
    shapes = sketch_def("0.2,0.2;L0.8,0.2;L0.8,0.8;L0.2,0.8;c", "0.5,0.3;Q0.7,0.5,0.5,0.7;Q0.3,0.5,0.5,0.3",
                        "0.0,1.0;C0.3,0.6,0.7,0.4,1.0,0.0")
    segs = [{"E_TEXTCTRL_SketchDef": d} for d in (zigzag, curves, shapes)]
    segs += [{"E_TEXTCTRL_SketchDef": shapes, "E_SLIDER_DrawPercentage": "100", "E_SLIDER_Thickness": "3"},
             {"E_TEXTCTRL_SketchDef": shapes, "E_CHECKBOX_MotionEnabled": "1", "E_SLIDER_MotionPercentage": "30"},
             {"E_TEXTCTRL_SketchDef": curves, "E_VALUECURVE_DrawPercentage":
              "Active=TRUE|Id=ID_VALUECURVE_DrawPercentage|Type=Ramp|Min=0.00|Max=100.00|P1=0.00|P2=100.00|RV=TRUE|"},
             {"E_TEXTCTRL_SketchDef": zigzag, "E_FILEPICKER_SketchBackground": IMAGE_FILE, "E_SLIDER_SketchBackgroundOpacity": "80"}]
    s = Sequence()
    place_segments(s, core_names, "Sketch", segs)
    out["Effect_Sketch"] = s

    # Glediator: raw frames on the Matrix (they're sized to its buffer), CSV
    # frames everywhere, through each duration treatment.
    s = Sequence()
    t = 0
    for treat in ("Normal", "Loop", "Slow/Accelerate"):
        s.add("Matrix", 0, "Glediator", {"E_FILEPICKERCTRL_Glediator_Filename": GLED_FILE,
                                         "E_CHOICE_Glediator_DurationTreatment": treat}, t, t + 2 * SEGMENT_MS)
        for m in core_names:
            if m != "Matrix":
                s.add(m, 0, "Glediator", {"E_FILEPICKERCTRL_Glediator_Filename": GLED_CSV_FILE,
                                          "E_CHOICE_Glediator_DurationTreatment": treat}, t, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    out["Effect_Glediator"] = s

    # Shader: the test ISF file's inputs (float, bool, long choice, point2D,
    # colour from the palette, event from a timing track), speed, offset,
    # zoom and lead-in.
    base = {"E_0FILEPICKERCTRL_IFS": SHADER_FILE, "E_CHOICE_SHADERXYZZY_pulse": "Beats"}
    segs = [{}]
    segs += [{"E_CHOICE_SHADERXYZZY_mode": mode} for mode in ("Stripes", "Checks")]
    segs += [{"E_SLIDER_SHADERXYZZY_scale": "1200"}, {"E_CHECKBOX_SHADERXYZZY_invert": "1"},
             {"E_SLIDER_SHADERXYZZY_centerX": "20", "E_SLIDER_SHADERXYZZY_centerY": "80"},
             {"E_VALUECURVE_SHADERXYZZY_scale":
              "Active=TRUE|Id=ID_VALUECURVE_SHADERXYZZY_scale|Type=Ramp|Min=100.00|Max=2000.00|P1=0.00|P2=100.00|RV=TRUE|"},
             {"E_SLIDER_Shader_Speed": "300"}, {"E_SLIDER_Shader_Offset_X": "40", "E_SLIDER_Shader_Offset_Y": "-30"},
             {"E_SLIDER_Shader_Zoom": "30"}, {"E_TEXTCTRL_Shader_LeadIn": "40"}]
    s = Sequence()
    place_segments(s, core_names, "Shader", segs, base=base)
    s.add_timing("Beats", beat_marks(s.end_ms))
    out["Effect_Shader"] = s
    return out


def model_type_scenarios():
    out = {}

    # The extra model types and layouts through a spread of buffer-shaped
    # effects, then the group through its buffer styles.
    s = Sequence()
    effects = [("On", {}), ("Color Wash", {}), ("Bars", {"E_CHOICE_Bars_Direction": "Left"}), ("Bars", {}),
               ("Spirals", {}), ("Butterfly", {}), ("Pinwheel", {}), ("Plasma", {}), ("Marquee", {}),
               ("SingleStrand", {}), ("Circles", {}), ("Bars", {"B_CHOICE_BufferStyle": "Per Preview"}),
               ("Spirals", {"B_CHOICE_BufferStyle": "Single Line"}), ("Bars", {"B_CHOICE_BufferStyle": "Horizontal Per Strand"}),
               ("Bars", {"B_CHOICE_BufferStyle": "Vertical Per Strand"}), ("Bars", {"B_CHOICE_BufferTransform": "Rotate CW 90"})]
    t = 0
    for effect, st in effects:
        for m in NEW_TYPES:
            s.add(m, 0, effect, st, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    for st in ("Default", "Per Preview", "Horizontal Per Model", "Vertical Per Model", "Single Line",
               "Overlay - Scaled", "Per Model Default", "Per Model Per Preview", "Per Model Default Deep"):
        s.add(NEW_TYPES_GROUP, 0, "Spirals", {"B_CHOICE_BufferStyle": st}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    out["Feature_ModelTypes"] = s

    # Every submodel form on its own matrix.
    s = Sequence()
    t = 0
    for sub in ("Window", "XY", "Stacked", "Reversed", "Dots"):
        for effect, st in (("Bars", {"E_CHOICE_Bars_Direction": "Left"}), ("Spirals", {}),
                           ("Bars", {"B_CHOICE_BufferStyle": "Per Preview"})):
            s.add(f"SM_Matrix/{sub}", 0, effect, st, t, t + SEGMENT_MS)
            t += SEGMENT_MS
    s.add("SM_Matrix", 0, "Color Wash", {}, 0, t)
    out["Feature_SubModelTypes"] = s

    # The skull's channels through DMX levels and ramps, its colour through
    # colour effects; the 3D servo model's servos through Servo.
    ramp = lambda vid: f"Active=TRUE|Id=ID_VALUECURVE_{vid}|Type=Ramp|Min=0.00|Max=255.00|P1=0.00|P2=100.00|RV=TRUE|"
    s = Sequence()
    t = 0
    for seg in ({f"E_SLIDER_DMX{c}": str(9 * c % 256) for c in range(1, 27)},
                {f"E_VALUECURVE_DMX{c}": ramp(f"DMX{c}") for c in range(1, 27)}):
        s.add("Skull", 0, "DMX", seg, t, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    for effect in ("On", "Color Wash"):
        s.add("Skull", 0, effect, {}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    t = 0
    for seg in ({"E_CHOICE_Channel": "Servo1", "E_TEXTCTRL_Servo": "10", "E_TEXTCTRL_EndValue": "90"},
                {"E_CHOICE_Channel": "Servo2", "E_TEXTCTRL_Servo": "80", "E_TEXTCTRL_EndValue": "20"},
                {"E_CHOICE_Channel": "Servo1", "E_TEXTCTRL_Servo": "50", "E_TEXTCTRL_EndValue": "50", "E_CHECKBOX_16bit": "0"}):
        s.add("Servo3D", 0, "Servo", seg, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    out["Effect_DMXSkullServo3D"] = s
    return out


def wled_names(src, table):
    """A JSON_*_names table from FX.h, in its original (WLED) order."""
    text = (src / "src-core" / "effects" / "FX.h").read_text(encoding="utf-8", errors="replace")
    start = text.index(f"const char {table}[]")
    body = text[text.index("[", text.index("R\"=====(", start)) + 1:text.index("]", text.index("R\"=====(", start))]
    return [n.strip().strip('"') for n in body.replace("\n", "").split(",") if n.strip()]


def variant_scenarios(src, core_names):
    out = {}

    # Single Strand's FX mode runs the WLED effect library (FX.cpp), which the
    # metadata walk never selects: the mode is a notebook tab and the effect
    # and palette lists are filled in at runtime from FX.h.
    s = Sequence()
    fx = {"E_NOTEBOOK_SSEFFECT_TYPE": "FX"}
    t = 0
    for mode in wled_names(src, "JSON_mode_names"):
        if mode in NONDETERMINISTIC_FX:
            continue
        for m in core_names:
            s.add(m, 0, "SingleStrand", dict(fx, E_CHOICE_SingleStrand_FX=mode), t, t + SEGMENT_MS // 2)
        t += SEGMENT_MS // 2
    for pal in wled_names(src, "JSON_palette_names"):
        for m in core_names:
            s.add(m, 0, "SingleStrand", dict(fx, E_CHOICE_SingleStrand_FX="Palette", E_CHOICE_SingleStrand_FX_Palette=pal),
                  t, t + SEGMENT_MS // 4)
        t += SEGMENT_MS // 4
    out["Effect_SingleStrandFX"] = s

    s = Sequence()
    t = 0
    for mode in NONDETERMINISTIC_FX:
        for m in core_names:
            s.add(m, 0, "SingleStrand", dict(fx, E_CHOICE_SingleStrand_FX=mode), t, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    out["Effect_SingleStrandFX_Phased"] = s
    meta = json.loads((src / "resources" / "effectmetadata" / "Video.json").read_text(encoding="utf-8"))

    # Video through the metadata segments, on every core model.
    s = Sequence()
    place_segments(s, core_names, "Video", effect_segments(meta), base={"E_FILEPICKERCTRL_Video_Filename": VIDEO_FILE})
    out["Effect_Video"] = s

    # Output variants: each node order / string type / curve sees solid
    # primaries, white, a mix and a moving effect.
    s = Sequence()
    solid = lambda c: f"C_BUTTON_Palette1={c},C_CHECKBOX_Palette1=1"
    segs = [("On", {}, solid(c)) for c in ("#FF0000", "#00FF00", "#0000FF", "#FFFFFF", "#806040")]
    segs += [("Color Wash", {}, None), ("Bars", {"E_CHOICE_Bars_Direction": "Left"}, None),
             ("Spirals", {"B_CHOICE_BufferStyle": "Per Preview"}, None)]
    t = 0
    for effect, st, pal in segs:
        for m in VARIANTS:
            s.add(m, 0, effect, st, t, t + SEGMENT_MS, palette=pal)
        t += SEGMENT_MS
    out["Feature_ModelOutput"] = s

    # Sequence frame rates other than 50 ms.
    for ms in (25, 100):
        s = Sequence(frame_ms=ms)
        t = 0
        for effect in ("Bars", "Butterfly", "Meteors", "Spirals"):
            for m in core_names:
                s.add(m, 0, effect, {}, t, t + SEGMENT_MS)
            t += SEGMENT_MS
        out[f"Seq_Timing{ms}ms"] = s

    # Model blending off: a group effect overlapping model effects.
    s = Sequence(model_blending=False)
    s.add(GROUP, 0, "Spirals", {}, 0, 3 * SEGMENT_MS)
    for m in core_names[:6]:
        s.add(m, 0, "Bars", {"E_CHOICE_Bars_Direction": "Left"}, SEGMENT_MS, 2 * SEGMENT_MS)
    out["Seq_NoModelBlending"] = s

    # Palette entries that are colour curves rather than fixed colours.
    curve = "Active=TRUE|Id=ID_BUTTON_Palette{n}|Values=x=0.000^c=#ff0000;x=0.500^c=#00ff00;x=1.000^c=#0000ff|"
    pal = PALETTE.replace("C_BUTTON_Palette1=#FF0000", "C_BUTTON_Palette1=" + curve.format(n=1)).replace(
        "C_BUTTON_Palette2=#00FF00", "C_BUTTON_Palette2=" + curve.format(n=2).replace("#ff0000", "#ffffff"))
    s = Sequence(palette=pal)
    t = 0
    for effect in ("Color Wash", "Bars", "Butterfly", "Spirals", "Twinkle"):
        for m in core_names:
            s.add(m, 0, effect, {}, t, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    out["Feature_PaletteCurves"] = s

    # Layer morph and the effect mix threshold between two layers.
    s = Sequence()
    t = 0
    for mix, morph in ((25, "0"), (75, "0"), (50, "1"), (100, "1")):
        for m in core_names:
            s.add(m, 0, "Butterfly", {"T_SLIDER_EffectLayerMix": str(mix), "T_CHECKBOX_LayerMorph": morph}, t, t + SEGMENT_MS)
            s.add(m, 1, "Spirals", {}, t, t + SEGMENT_MS)
        t += SEGMENT_MS
    out["Feature_LayerMorph"] = s

    # Sparkles, plain and driven by the audio.
    s = Sequence(media=AUDIO_FILE)
    t = 0
    for st in ({"C_SLIDER_SparkleFrequency": "120"},
               {"C_SLIDER_SparkleFrequency": "120", "C_CHECKBOX_MusicSparkles": "1"},
               {"C_SLIDER_SparkleFrequency": "60", "C_CHECKBOX_MusicSparkles": "1", "C_COLOURPICKERCTRL_SparklesColour": "#00FFFF"}):
        for m in core_names:
            s.add(m, 0, "Color Wash", st, t, t + 2 * SEGMENT_MS)
        t += 2 * SEGMENT_MS
    out["Feature_Sparkles"] = s
    return out


def write_wav(path):
    """Kick on every beat, a slow 100Hz-4kHz sweep and a quiet chord."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    phase = 0.0
    for i in range(AUDIO_SECONDS * AUDIO_RATE):
        t = i / AUDIO_RATE
        beat = t % 0.5
        kick = math.exp(-beat * 30) * math.sin(2 * math.pi * 60 * beat)
        freq = 100 * (40 ** ((t % 15) / 15))
        phase += 2 * math.pi * freq / AUDIO_RATE
        sweep = 0.3 * math.sin(phase)
        chord = 0.1 * (math.sin(2 * math.pi * 262 * t) + math.sin(2 * math.pi * 330 * t) + math.sin(2 * math.pi * 392 * t))
        v = max(-1.0, min(1.0, 0.6 * kick + sweep + chord))
        frames += struct.pack("<h", int(v * 30000))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(AUDIO_RATE)
        w.writeframes(bytes(frames))


def write_png(path, w=32, h=16):
    """Horizontal hue gradient over a vertical brightness ramp."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = b""
    for y in range(h):
        row = b"\x00"
        for x in range(w):
            r, g, b = (int(255 * (0.5 + 0.5 * math.cos(2 * math.pi * (x / w + o)))) for o in (0, 1 / 3, 2 / 3))
            k = (y + 1) / h
            row += bytes((int(r * k), int(g * k), int(b * k)))
        rows += row

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


SHADER_SOURCE = """/*{
    "DESCRIPTION": "xlights-tests pattern: rings, stripes or checks",
    "CREDIT": "xlights-tests",
    "ISFVSN": "2",
    "CATEGORIES": ["Generator"],
    "INPUTS": [
        {"NAME": "scale", "TYPE": "float", "DEFAULT": 4.0, "MIN": 1.0, "MAX": 20.0},
        {"NAME": "invert", "TYPE": "bool", "DEFAULT": false},
        {"NAME": "mode", "TYPE": "long", "VALUES": [0, 1, 2], "LABELS": ["Rings", "Stripes", "Checks"], "DEFAULT": 0},
        {"NAME": "center", "TYPE": "point2D", "DEFAULT": [0.5, 0.5], "MIN": [0.0, 0.0], "MAX": [1.0, 1.0]},
        {"NAME": "tint", "TYPE": "color", "DEFAULT": [1.0, 0.5, 0.0, 1.0]},
        {"NAME": "pulse", "TYPE": "event"}
    ]
}*/

void main() {
    vec2 uv = isf_FragNormCoord;
    float v;
    if (mode == 0) {
        v = 0.5 + 0.5 * sin(distance(uv, center) * scale * 6.2832 - TIME * 3.0);
    } else if (mode == 1) {
        v = 0.5 + 0.5 * sin(uv.x * scale * 6.2832 + TIME * 2.0);
    } else {
        v = mod(floor(uv.x * scale) + floor(uv.y * scale + TIME), 2.0);
    }
    if (invert) {
        v = 1.0 - v;
    }
    if (pulse) {
        v = 1.0;
    }
    gl_FragColor = vec4(tint.rgb * v, 1.0);
}
"""


def write_shader(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SHADER_SOURCE, encoding="utf-8", newline="\n")


def gled_frame(f, w, h):
    """A diagonal colour sweep that moves one pixel per frame."""
    px = []
    for y in range(h):
        for x in range(w):
            k = (x + y + f) % 12
            px += [255 if k < 4 else 0, 255 if 4 <= k < 8 else 0, 255 if k >= 8 else 0]
    return px


def write_glediator(raw_path, csv_path):
    w, h = GLED_SIZE
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"".join(bytes(gled_frame(f, w, h)) for f in range(GLED_FRAMES)))
    # CSV frames hold one grey level per pixel, not RGB triples.
    csv_path.write_text("".join(",".join(str((x + y + f) * 16 % 256) for y in range(h) for x in range(w)) + "\n"
                                for f in range(GLED_FRAMES)), encoding="utf-8", newline="\n")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.xsq"):
        old.unlink()

    model_list = models()
    names = [m[0] for m in model_list]
    channels = write_rgbeffects(out / "xlights_rgbeffects.xml", model_list + extra_models(), names)
    write_networks(out / "xlights_networks.xml", channels)
    elements = names + [GROUP, MIXED_GROUP]
    write_wav(out / AUDIO_FILE)
    write_png(out / IMAGE_FILE)
    write_shader(out / SHADER_FILE)
    write_glediator(out / GLED_FILE, out / GLED_CSV_FILE)

    scenarios = {}
    for f in sorted((src / "resources" / "effectmetadata").glob("*.json")):
        if f.name.startswith("_"):
            continue
        meta = json.loads(f.read_text(encoding="utf-8"))
        effect = meta.get("effectName")
        if not effect or effect in SKIP_EFFECTS:
            continue
        seq = Sequence()
        place_segments(seq, names, effect, effect_segments(meta), canvas=bool(meta.get("canvasMode")))
        scenarios["Effect_" + effect.replace(" ", "")] = seq
    scenarios.update(input_scenarios(src, names))
    scenarios.update(dmx_scenarios())
    scenarios.update(music_scenarios(names))
    scenarios.update(model_type_scenarios())
    scenarios.update(variant_scenarios(src, names))
    scenarios.update(feature_sequences(names))

    for name, seq in scenarios.items():
        seq.write(out / f"{name}.xsq", elements)

    (out / "scenarios.json").write_text(json.dumps({
        "channels": channels,
        "frame_ms": FRAME_MS,
        "scenarios": {n: {"expected_failure": EXPECTED.get(n)} for n in sorted(scenarios)},
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{len(scenarios)} scenarios, {len(model_list) + len(extra_models())} models, {channels} channels -> {out}")


if __name__ == "__main__":
    main()
