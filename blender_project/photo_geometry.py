"""Editable photo details, built in centimetres with source metadata."""
import bpy


def box(name, bounds, collection, mat, prism, metadata):
    x0, x1, y0, y1, z0, z1 = bounds
    if not (x1 > x0 and y1 > y0 and z1 > z0):
        raise ValueError(f"Invalid bounds: {name}: {bounds}")
    return prism(name, [(x0,y0), (x1,y0), (x1,y1), (x0,y1)],
                 z0 / 100, z1 / 100, collection, mat, metadata)


def build_photos(data, root, child_collection, material, prism):
    frames = child_collection(root, "09 ОКНА - рамы и створки")
    glazing = child_collection(root, "10 ОКНА - стекло")
    beams = child_collection(root, "11 БАЛКИ И НИШИ - по фото")
    balcony = child_collection(root, "12 БАЛКОН - ограждение условно")
    frame = material("Photo / graphite frames", (0.14, 0.17, 0.18, 1), 0.3)
    rubber = material("Photo / rubber seals", (0.035, 0.045, 0.05, 1), 0.55)
    steel = material("Photo / handle", (0.3, 0.34, 0.36, 1), 0.25)
    steel.node_tree.nodes['Principled BSDF'].inputs['Metallic'].default_value = 0.7
    plaster = material("Photo / beam plaster", (0.72, 0.71, 0.67, 1), 0.85)
    glass = material("Photo / clear glass", (0.69, 0.83, 0.86, 0.22), 0.12)
    glass.surface_render_method = "BLENDED"
    nodes = glass.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    mix = nodes.new('ShaderNodeMixShader')
    mix.inputs[0].default_value = 0.16
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    glossy = nodes.new('ShaderNodeBsdfPrincipled')
    glossy.inputs['Base Color'].default_value = (0.48,0.7,0.76,1)
    glossy.inputs['Roughness'].default_value = 0.14
    glossy.inputs['Metallic'].default_value = 0.25
    glass.node_tree.links.new(transparent.outputs[0], mix.inputs[1])
    glass.node_tree.links.new(glossy.outputs[0], mix.inputs[2])
    glass.node_tree.links.new(mix.outputs[0], output.inputs['Surface'])

    for w in data['windows']:
        name, x0, x1, y, h, t = w['id'], w['x_min'], w['x_max'], w['y'], w['height'], w['transom_z']
        middle = x0 + (x1-x0)*w['split_fraction']
        meta = {k:w[k] for k in ('room','source','certainty')}
        meta['feature_id'] = name
        meta['purchase_ready'] = False
        def part(label, bounds, mat=frame, coll=frames):
            return box(f"{name} / {label}", bounds, coll, mat, prism, meta)
        def rectangle(label, left, right, bottom, top, depth, width=5):
            part(label+' left', [left,left+width,y-depth,y+depth,bottom,top])
            part(label+' right', [right-width,right,y-depth,y+depth,bottom,top])
            part(label+' bottom', [left+width,right-width,y-depth,y+depth,bottom,bottom+width])
            part(label+' top', [left+width,right-width,y-depth,y+depth,top-width,top])
        rectangle('outer frame',x0,x1,0,h,3.5,5)
        part('transom rail',[x0+5,x1-5,y-3.5,y+3.5,t-3,t+3])
        part('central mullion',[middle-3,middle+3,y-3.5,y+3.5,5,t-3])
        for leaf,l,r in [('left',x0+5,middle-3),('right',middle+3,x1-5)]:
            rectangle(leaf+' sash',l+0.4,r-0.4,5.4,t-3.4,4.3,4)
            part(leaf+' glass',[l+4.4,r-4.4,y-0.3,y+0.3,9.4,t-7.4],glass,glazing)
            part(leaf+' seal left',[l+4,l+4.5,y+4.31,y+4.5,9.4,t-7.4],rubber)
        part('transom glass',[x0+5,x1-5,y-0.3,y+0.3,t+3,h-5],glass,glazing)
        handle_x = middle-9 if w['active_leaf']=='left' else middle+9
        part('handle base',[handle_x-1.2,handle_x+1.2,y+4.4,y+5.4,99,110],steel)
        part('handle stem',[handle_x-0.8,handle_x+0.8,y+5.4,y+8,103,105],steel)
        part('handle lever',[handle_x-1,handle_x+1,y+7,y+9,94,105],steel)
        hinge_x = x0+7 if w['active_leaf']=='left' else x1-7
        for z in (35,110,185):
            part('hinge '+str(z),[hinge_x-1,hinge_x+1,y+4,y+6,z,z+8],steel)
        part('threshold',[x0,x1,y-5,y+7,0,2],steel)

    for s in data['solids']:
        meta = {k:s[k] for k in ('room','source','certainty')}
        meta['feature_id'] = s['id']
        meta['purchase_ready'] = False
        box(s['id'], s['bounds'], beams, plaster, prism, meta)

    meta = {'source':'ЗалИСпальняРазмерыПроход.jpg; спальнябезразмеров.jpg',
            'certainty':'balcony rail visible; all dimensions and position approximate', 'purchase_ready':False}
    rail = material('Photo / balcony metal', (0.22,0.27,0.29,1),0.5)
    box('Balcony / opaque guard panel',[0,616,-119,-117,12,98],balcony,rail,prism,meta)
    box('Balcony / handrail',[0,616,-122,-116,108,112],balcony,frame,prism,meta)
    for x in range(0,617,77):
        box('Balcony / post '+str(x),[x,x+3,-121,-118,0,112],balcony,frame,prism,meta)
    door_mat = material('Photo / entrance door', (0.045,0.055,0.06,1),0.65)
    meta = {'room':'living_kitchen', 'source':'ВходКухняСразмерами.jpg',
            'certainty':'entrance door visible; opening position, 108 width and 210 height provisional', 'purchase_ready':False}
    box('LK entrance door / provisional',[337,445,768,773,0,210],frames,door_mat,prism,meta)
    box('LK entrance lintel / provisional',[337,445,764.5,776.5,210,300],beams,plaster,prism,meta)
    box('LK entrance handle',[346,357,766,768,98,100],frames,steel,prism,meta)
    return frames, glazing, beams, balcony
