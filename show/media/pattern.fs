/*{
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
