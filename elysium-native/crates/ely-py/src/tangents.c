/* Elysium's adapter; upstream MikkTSpace remains unmodified. */
#include "mikktspace.h"
#include <string.h>
typedef struct {
    int faces;
    const int *offsets;
    const float *positions, *normals, *uvs;
    float *out;
} ElyTangents;
static int faces(const SMikkTSpaceContext *c) { return ((ElyTangents *)c->m_pUserData)->faces; }
static int vertices(const SMikkTSpaceContext *c, int f) {
    const int *o = ((ElyTangents *)c->m_pUserData)->offsets;
    return o[f + 1] - o[f];
}
static void position(const SMikkTSpaceContext *c, float *v, int f, int k) {
    ElyTangents *d = c->m_pUserData;
    memcpy(v, d->positions + 3 * (d->offsets[f] + k), 3 * sizeof(float));
}
static void normal(const SMikkTSpaceContext *c, float *v, int f, int k) {
    ElyTangents *d = c->m_pUserData;
    memcpy(v, d->normals + 3 * (d->offsets[f] + k), 3 * sizeof(float));
}
static void uv(const SMikkTSpaceContext *c, float *v, int f, int k) {
    ElyTangents *d = c->m_pUserData;
    memcpy(v, d->uvs + 2 * (d->offsets[f] + k), 2 * sizeof(float));
}
static void tangent(const SMikkTSpaceContext *c, const float *v, float sign, int f, int k) {
    ElyTangents *d = c->m_pUserData;
    float *out = d->out + 4 * (d->offsets[f] + k);
    memcpy(out, v, 3 * sizeof(float));
    out[3] = sign;
}
int ely_corner_tangents(int count, const int *offsets, const float *p, const float *n,
                        const float *uvs, float *out) {
    ElyTangents data = {count, offsets, p, n, uvs, out};
    SMikkTSpaceInterface api = {faces, vertices, position, normal, uv, tangent, 0};
    SMikkTSpaceContext context = {&api, &data};
    return genTangSpaceDefault(&context);
}
