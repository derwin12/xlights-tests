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

# Effects the generic metadata walk can't drive. Faces, State, Pictures,
# VU Meter, Music and Duplicate get hand-written scenarios further down; the
# rest need DMX fixtures, MIDI, video, shaders or sketch files.
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
}


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


GROUP = "All Models"
MIXED_GROUP = "Mixed Group"

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


def write_rgbeffects(path, model_list):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<xrgb>", '  <models type="rgb_effects">']
    ch = 1
    for name, display, attrs, nodes, x, y in model_list:
        a = dict(name=name, DisplayAs=display, StringType="RGB Nodes", StartChannel=ch,
                 StartSide="B", Dir="L", Antialias=1, PixelSize=2, Transparency=0,
                 LayoutGroup="Default", versionNumber=8, WorldPosX=x, WorldPosY=y, WorldPosZ=0)
        a.update(attrs)
        open_tag = "    <model " + " ".join(f"{k}={quoteattr(str(v))}" for k, v in a.items())
        kids = CHILDREN.get(name)
        if kids:
            lines.append(open_tag + ">")
            lines += ["      " + k for k in kids]
            lines.append("    </model>")
        else:
            lines.append(open_tag + " />")
        ch += nodes * 3
    lines.append("  </models>")
    lines.append('  <modelGroups type="rgb_effects">')
    names = ",".join(m[0] for m in model_list)
    lines.append(f'    <modelGroup name={quoteattr(GROUP)} DisplayAs="ModelGroup" DefaultCamera="2D" '
                 f'GridSize="400" layout="minimalGrid" LayoutGroup="Default" models={quoteattr(names)} />')
    lines.append(f'    <modelGroup name={quoteattr(MIXED_GROUP)} DisplayAs="ModelGroup" DefaultCamera="2D" '
                 f'GridSize="400" layout="minimalGrid" LayoutGroup="Default" '
                 f'models="Matrix/Top,Tree/Bottom,Star,Circle,Spinner" />')
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

    def __init__(self, media=None):
        self.placements = []
        self.end_ms = 0
        self.media = media
        self.timing = {}  # name -> list of layers, each a list of (label, start, end)

    def add_timing(self, name, *layers):
        self.timing[name] = [list(l) for l in layers]

    def add(self, element, layer, effect, settings, start, end):
        self.placements.append((element, layer, effect, settings, start, end))
        self.end_ms = max(self.end_ms, end)

    def write(self, path, element_names):
        db = []
        db_index = {}
        per_element = {e: {} for e in element_names}
        per_sub = {e: {} for e in element_names}
        for element, layer, effect, settings, start, end in self.placements:
            key = ",".join(f"{k}={v}" for k, v in sorted(settings.items()))
            if key not in db_index:
                db_index[key] = len(db)
                db.append(key)
            if "/" in element:
                parent, sub = element.split("/", 1)
                per_sub[parent].setdefault(sub, []).append((effect, db_index[key], start, end))
            else:
                per_element[element].setdefault(layer, []).append((effect, db_index[key], start, end))

        duration = (self.end_ms + 500) / 1000.0
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<xsequence BaseChannel="0" ChanCtrlBasic="0" ChanCtrlColor="0" FixedPointTiming="1" ModelBlending="true">',
               "  <head>",
               "    <version>2026.1</version>",
               "    <author>xlights-tests</author>",
               f"    <sequenceTiming>{FRAME_MS} ms</sequenceTiming>",
               f"    <sequenceType>{'Media' if self.media else 'Animation'}</sequenceType>",
               f"    <mediaFile>{escape(self.media or '')}</mediaFile>",
               f"    <sequenceDuration>{duration:.3f}</sequenceDuration>",
               "  </head>",
               "  <ColorPalettes>",
               f"    <ColorPalette>{PALETTE}</ColorPalette>",
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
                for effect, ref, start, end in sorted(layers.get(layer, []), key=lambda p: p[2]):
                    out.append(f'        <Effect ref="{ref}" name={quoteattr(effect)} startTime="{start}" endTime="{end}" palette="0" />')
                out.append("      </EffectLayer>")
            for sub, effs in per_sub[e].items():
                out.append(f'      <SubModelEffectLayer name={quoteattr(sub)}>')
                for effect, ref, start, end in sorted(effs, key=lambda p: p[2]):
                    out.append(f'        <Effect ref="{ref}" name={quoteattr(effect)} startTime="{start}" endTime="{end}" palette="0" />')
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


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.xsq"):
        old.unlink()

    model_list = models()
    channels = write_rgbeffects(out / "xlights_rgbeffects.xml", model_list)
    write_networks(out / "xlights_networks.xml", channels)
    names = [m[0] for m in model_list]
    elements = names + [GROUP, MIXED_GROUP]
    write_wav(out / AUDIO_FILE)
    write_png(out / IMAGE_FILE)

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
    scenarios.update(feature_sequences(names))

    for name, seq in scenarios.items():
        seq.write(out / f"{name}.xsq", elements)

    (out / "scenarios.json").write_text(json.dumps({
        "channels": channels,
        "frame_ms": FRAME_MS,
        "scenarios": {n: {"expected_failure": EXPECTED.get(n)} for n in sorted(scenarios)},
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{len(scenarios)} scenarios, {len(model_list)} models, {channels} channels -> {out}")


if __name__ == "__main__":
    main()
