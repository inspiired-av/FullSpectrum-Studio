"""Experimental display-only, topology-local color-preserving vertex clustering.

Only merges vertices that are connected by original edges AND lie in the same
spatial cell; preserves original per-face and per-corner color attributes of
surviving faces. Does not change the source/export mesh. This is a preview
approximation, not a topology-preserving or exact-color-surface simplifier.
"""
from __future__ import annotations
from dataclasses import dataclass
from dataclasses import replace
from time import perf_counter
import math

@dataclass(frozen=True)
class ClusterResult:
    mesh: object
    reason: str
    duration_ms: float
    source_faces: int
    draw_faces: int
    area_relative_error: float
    worst_color_area_error: float
    dropped_colors: int


def build_cluster_lod(mesh, mode='balanced', *, cells=None, cancelled=None, max_seconds=8.0):
    import numpy as np
    start = perf_counter()
    faces = np.asarray(mesh.triangles, dtype=np.int32)
    points = np.asarray(mesh.vertices, dtype=np.float64)
    n = len(faces)
    default = ClusterResult(mesh, 'Full detail; unsafe or negligible simplification', 0., n, n, 0., 0., 0)
    if n < 150 or n > 750_000 or len(points) > 1_500_000 or len(points) == 0 or mode not in ('balanced', 'performance'):
        return default
    if cancelled is not None and cancelled():
        return default
    # Scale grid width to sampled local edge spacing, rather than overall
    # bounding-box diameter alone (which behaves poorly for tiny models).
    # Fixed override is only for reproducible experimental benchmarks.
    sample = faces[::max(1,n//20_000)]
    edge_sample = np.concatenate((sample[:,[0,1]],sample[:,[1,2]],sample[:,[2,0]]))
    local_lengths = np.linalg.norm(points[edge_sample[:,0]]-points[edge_sample[:,1]],axis=1)
    typical = float(np.median(local_lengths[local_lengths>1.e-12])) if (local_lengths>1.e-12).any() else 0.0
    div = int((points.max(axis=0)-points.min(axis=0)).max() /
              (typical*(0.45 if mode=='balanced' else 0.65))) if cells is None and typical>0 else int(cells or 512)
    div = max(16,min(20000,div))
    if div < 4 or div > 20000:
        raise ValueError('Invalid LOD grid resolution')
    low = points.min(axis=0)
    high = points.max(axis=0)
    extent = float((high-low).max())
    if not math.isfinite(extent) or extent <= 0:
        return default
    # With at most 20,001^3 cell coordinates, the code fits in signed int64.
    bins = np.floor((points-low)*(div/extent)).astype(np.int64)
    bins = np.minimum(bins,div)
    key = bins[:,0]+(div+1)*(bins[:,1]+(div+1)*bins[:,2])
    # Protect all vertices of faces with independently interpolated colors.
    corner = getattr(mesh,'corner_colors', ())
    protected = np.zeros(len(points), dtype=np.bool_)
    if len(corner)==n:
        gradient = np.fromiter((len(set(c)) != 1 for c in corner),
                               dtype=np.bool_, count=n)
        protected[faces[gradient].reshape(-1)] = True
    source_colors=getattr(mesh,'face_colors', ())
    if len(source_colors)!=n:
        return default
    # Candidate topologies are built from actual mesh edges, never from arbitrary
    # vertices merely close together in 3D (disconnected shells remain separate).
    edges = np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]))
    # Verify source topology and lock existing open borders. If an input has
    # non-manifold edges, the experimental simplifier leaves it untouched.
    unique_edges, source_counts = np.unique(np.sort(edges,axis=1), axis=0,return_counts=True)
    source_open = int(np.count_nonzero(source_counts==1))
    source_verts = int(len(np.unique(faces)))
    original_euler = source_verts - len(unique_edges) + n
    if np.any(source_counts>2):
        return ClusterResult(mesh,'Non-manifold source: full detail retained',
                             (perf_counter()-start)*1000,n,n,0.,0.,0)
    if source_open:
        protected[unique_edges[source_counts==1].reshape(-1)]=True
    orig=points[faces]
    norm=np.cross(orig[:,1]-orig[:,0],orig[:,2]-orig[:,0])
    orig_len=np.linalg.norm(norm,axis=1)
    area=orig_len*.5
    stop_cos=(math.cos(math.radians(40)) if mode=='balanced' else
              math.cos(math.radians(55)))
    # Validation retries can freeze the local vertices surrounding damaged
    # faces. Never ship a candidate that retained a reversed face.
    tries=0
    deadline=start+max(0.25,float(max_seconds))
    while True:
        if (cancelled is not None and cancelled()) or perf_counter()>deadline:
            return ClusterResult(mesh,'LOD cancelled or exceeded time budget',
                                 (perf_counter()-start)*1000,n,n,0.,0.,0)
        parent = np.arange(len(points), dtype=np.int32)
        size = np.ones(len(points), dtype=np.int32)
        active = ((key[edges[:,0]]==key[edges[:,1]]) &
                  (~protected[edges[:,0]]) & (~protected[edges[:,1]]))
        possible=edges[active]
        for j,(u,v) in enumerate(possible):
            if cancelled is not None and j%16384==0 and cancelled():
                return default
            u=int(u);v=int(v)
            while parent[u]!=u:
                parent[u]=parent[parent[u]];u=int(parent[u])
            while parent[v]!=v:
                parent[v]=parent[parent[v]];v=int(parent[v])
            if u!=v:
                if size[u]<size[v]:u,v=v,u
                parent[v]=u;size[u]+=size[v]
        for u in range(len(parent)):
            v=u
            while parent[v]!=v:
                parent[v]=parent[parent[v]];v=int(parent[v])
            parent[u]=v
        _,inv=np.unique(parent,return_inverse=True)
        mapped=inv[faces]
        keep=(mapped[:,0]!=mapped[:,1])&(mapped[:,1]!=mapped[:,2])&(mapped[:,0]!=mapped[:,2])
        if keep.sum()> n*.96:
            return default
        means=np.zeros((int(inv.max())+1,3),dtype=np.float64)
        np.add.at(means,inv,points)
        means/=np.bincount(inv,minlength=len(means))[:,None]
        proposed=means[mapped]
        new_norm=np.cross(proposed[:,1]-proposed[:,0],proposed[:,2]-proposed[:,0])
        new_len=np.linalg.norm(new_norm,axis=1)
        dot=np.einsum('ij,ij->i',norm,new_norm)
        # Only legitimate nondegenerate retained faces need orientation checks.
        good=(orig_len>1.e-14)&keep
        bad=good & ((dot <= 0) | (dot < stop_cos * orig_len*new_len))
        if not bad.any():
            # Reject/repair new non-manifold edges and new holes. The existing
            # topology must remain manifold with the same boundary count.
            candidate_edges = np.concatenate((mapped[keep][:,[0,1]],
                                              mapped[keep][:,[1,2]],
                                              mapped[keep][:,[2,0]]))
            output_edges, output_count=np.unique(
                np.sort(candidate_edges,axis=1),axis=0,return_counts=True)
            wrong= (output_count>2) | (output_count==1 if source_open==0 else output_count==0)
            open_count=int(np.count_nonzero(output_count==1))
            # Euler characteristic catches many hidden bow-ties or topological
            # changes that per-edge incidence tests alone might miss.
            output_euler=(int(len(np.unique(mapped[keep]))) -
                          int(len(output_edges)) + int(np.count_nonzero(keep)))
            if not wrong.any() and open_count==source_open and output_euler==original_euler:
                break
            if wrong.any():
                # Lock *entire spatial clusters*, not just one representative,
                # to undo any ambiguous non-manifold vertex fusion.
                groups=np.unique(output_edges[wrong].reshape(-1))
                protected[np.isin(inv,groups)] = True
            else:
                return ClusterResult(mesh,'Rejected: topology or Euler mismatch',
                        (perf_counter()-start)*1000,n,n,0.,0.,0)
            tries+=1
            if tries>=16:
                return ClusterResult(mesh,'Rejected: topology repair limit',
                        (perf_counter()-start)*1000,n,n,0.,0.,0)
            continue
        if tries>=16:
            return ClusterResult(mesh,'Rejected: normal-direction validation failed',
                                 (perf_counter()-start)*1000,n,n,0.,0.,0)
        protected[np.isin(inv, np.unique(inv[faces[bad].reshape(-1)]))] = True
        tries+=1
    area_new=new_len*.5
    # Color distribution = 3D area weighted, not simply triangle frequency.
    color_ids,ci=np.unique(np.asarray(source_colors,dtype=str),return_inverse=True)
    orig_area=np.bincount(ci,weights=area,minlength=len(color_ids))
    reduced_area=np.bincount(ci,weights=np.where(keep,area_new,0),minlength=len(color_ids))
    kept_counts=np.bincount(ci,weights=keep.astype(np.int8),minlength=len(color_ids))
    lost=kept_counts==0
    ratios=np.abs(reduced_area-orig_area)/np.maximum(orig_area,1.e-8)
    total_original=orig_area.sum()
    # Tiny material islands still cannot disappear; large color regions must
    # preserve close area coverage.
    significant=orig_area>total_original*.001
    max_error=float(ratios[significant].max()) if significant.any() else 0.0
    total_error=float(abs(reduced_area.sum()-total_original)/max(total_original,1.e-8))
    if lost.any() or total_error>(.025 if mode=='balanced' else .055) or max_error>(.075 if mode=='balanced' else .15):
        return ClusterResult(mesh,'Rejected: color-region area changed too much', (perf_counter()-start)*1000,n,n,total_error,max_error,int(lost.sum()))
    tris=np.asarray(mapped[keep],dtype=np.int32)
    # Compact unused clusters and remap colors without changing their codes.
    unique,reverse=np.unique(tris,return_inverse=True)
    compact_vertices=tuple(map(tuple,means[unique].tolist()))
    compact_faces=tuple(map(tuple,reverse.reshape((-1,3)).tolist()))
    use_idx=np.flatnonzero(keep)
    new_colors=tuple(source_colors[i] for i in use_idx)
    new_corners=tuple(corner[i] for i in use_idx) if len(corner)==n else ()
    lod=replace(mesh,vertices=compact_vertices,triangles=compact_faces,
                face_colors=new_colors,corner_colors=new_corners,
                render_buffer=None,load_profile=None)
    reduction=100*(1-len(compact_faces)/n)
    reason=('Experimental multicolor LOD: %.1f%% fewer faces; '
            'color-area change %.2f%% overall / %.2f%% worst significant color; '
            'original paint and export unchanged; appearance approximate' %
            (reduction,100*total_error,100*max_error))
    fields=getattr(mesh,'__dataclass_fields__',{})
    if 'render_indexed' in fields:
        lod=replace(lod,render_indexed=None)
    return ClusterResult(lod,reason,
                         (perf_counter()-start)*1000,n,len(compact_faces),total_error,max_error,0)


def build_adaptive_multicolor_lod(mesh, mode='balanced', *, max_seconds=12.0,
                                  cancelled=None):
    """Try a few bounded cell sizes; reject candidates with failed fidelity gates.

    Opt-in display LOD only. No implicit dependency on meshoptimizer or export.
    The source is immutable; every rejected candidate leaves full detail intact.
    """
    import numpy as np
    start=perf_counter()
    count=len(mesh.triangles)
    if mode not in ('balanced','performance') or count<150 or count>750_000:
        return ClusterResult(mesh,'Full detail retained',0.,count,count,0.,0.,0)
    f=np.asarray(mesh.triangles,dtype=np.int32)
    v=np.asarray(mesh.vertices,dtype=np.float64)
    if not len(v):
        return ClusterResult(mesh,'Empty source geometry',0.,count,count,0.,0.,0)
    if len(getattr(mesh,'corner_colors',()))==count:
        gradients=sum(len(set(t))>1 for t in mesh.corner_colors)
        if gradients>=count*.9:
            return ClusterResult(mesh,'Most source faces use protected interpolated gradients',
                                 (perf_counter()-start)*1000,count,count,0.,0.,0)
    sample=f[::max(1,count//20_000)]
    e=np.concatenate((sample[:,[0,1]],sample[:,[1,2]],sample[:,[2,0]]))
    lengths=np.linalg.norm(v[e[:,0]]-v[e[:,1]],axis=1)
    positive=lengths[lengths>1.e-12]
    if not len(positive):
        return ClusterResult(mesh,'Degenerate source edges',0.,count,count,0.,0.,0)
    median=float(np.median(positive))
    extent=float((v.max(axis=0)-v.min(axis=0)).max())
    scale=0.45 if mode=='balanced' else 0.65
    base=max(16,min(20000,int(extent/(median*scale))))
    best=None
    target_fraction = .70 if mode=='balanced' else .45
    for fraction in (1.0,.85,.70,.55,.40,.28):
        if cancelled is not None and cancelled():
            break
        elapsed=perf_counter()-start
        if elapsed>=max_seconds:
            break
        candidate=build_cluster_lod(mesh,mode,cells=max(16,int(base*fraction)),
                                    max_seconds=max(.25,max_seconds-elapsed),
                                    cancelled=cancelled)
        if candidate.draw_faces<count and (best is None or
              abs(candidate.draw_faces/count-target_fraction) <
              abs(best.draw_faces/count-target_fraction)):
            best=candidate
            if abs(candidate.draw_faces/count-target_fraction) <= (.06 if mode=='balanced' else .08):
                break
    if best is None:
        return ClusterResult(mesh,'No safe multicolor LOD met the fidelity checks',
                             (perf_counter()-start)*1000,count,count,0.,0.,0)
    return replace(best,duration_ms=(perf_counter()-start)*1000)
