# render 2d

import struct, ctypes

import sdl2
import sdl2.events
import sdl2.video
import sdl2.surface
import sdl2.blendmode
import sdl2.pixels
import sdl2.render
import sdl2.sdlgfx
import sdl2.sdlimage

def init():
    sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_NOPARACHUTE)
    sdl2.sdlimage.IMG_Init(0xffffffff)

def fini():
    sdl2.sdlimage.IMG_Quit()
    sdl2.SDL_Quit()

_bars = []
def bufpal2surface(buf, w, h, pal):
    # and also buf might be shorter that w*h,
    # so pad it with transparency
    surf = RGBAsurface(w, h)
    pitch = surf.contents.pitch
    bar = bytearray(pitch*h)
    for y in range(h):
        for x in range(w):
            bar[4*x + pitch*y + 0] = pal[buf[x+y*w]][0] if x+y*w < len(buf) else 0
            bar[4*x + pitch*y + 1] = pal[buf[x+y*w]][1] if x+y*w < len(buf) else 0
            bar[4*x + pitch*y + 2] = pal[buf[x+y*w]][2] if x+y*w < len(buf) else 0
            bar[4*x + pitch*y + 3] = pal[buf[x+y*w]][3] if x+y*w < len(buf) else 0
    _bars.append(bar) # leak a ref
    return RGBAsurface(w, h, bar)

def file2surface(fname):
    return sdl2.sdlimage.IMG_Load(fname.encode("utf-8"))

ctypes.pythonapi.PyByteArray_AsString.restype = ctypes.c_void_p
def bar2voidp(bar):
    bar_p =  ctypes.c_void_p(id(bar))
    return ctypes.c_void_p(ctypes.pythonapi.PyByteArray_AsString(bar_p))

def RGBAsurface(w, h, data = None):
    bpp   = ctypes.c_int()
    rmask = ctypes.c_uint()
    gmask = ctypes.c_uint()
    bmask = ctypes.c_uint()
    amask = ctypes.c_uint()
    sdl2.pixels.SDL_PixelFormatEnumToMasks(sdl2.pixels.SDL_PIXELFORMAT_ABGR8888,
        ctypes.byref(bpp), ctypes.byref(rmask), ctypes.byref(gmask), ctypes.byref(bmask), ctypes.byref(amask))

    if data is not None:
        if type(data) is bytearray:
            data_ptr =  bar2voidp(data)
        elif type(data) is bytes:
            data_ptr =  bytes2voidp(data)
        else:
            data_ptr = None
        rv = sdl2.surface.SDL_CreateRGBSurfaceFrom(data_ptr, w, h, bpp, w*4, rmask, gmask, bmask, amask)
    else:
        rv = sdl2.surface.SDL_CreateRGBSurface(0, w, h, bpp, rmask, gmask, bmask, amask)
    sdl2.SDL_SetSurfaceBlendMode(rv, sdl2.SDL_BLENDMODE_NONE)
    return rv

def draw_textris(window, renderer, vtxlist, trilist, texmap, plist, poilist, countrylabels, mzquads):
    sdl2.render.SDL_SetRenderDrawColor(renderer, 0x10, 0x10, 0x80, 0xff)
    sdl2.render.SDL_RenderClear(renderer)

    vp = sdl2.rect.SDL_Rect()
    sdl2.render.SDL_RenderGetViewport(renderer, ctypes.byref(vp))    
    wscale = vp.w/2
    hscale = vp.h/2
    woff = vp.w/2
    hoff = vp.h/2

    csp_t = ctypes.POINTER(ctypes.c_short)
    ar_x = (ctypes.c_short*3)()
    ar_y = (ctypes.c_short*3)()
    for tri in trilist:
        texi, ai, bi, ci = tri
        a = vtxlist[ai]
        b = vtxlist[bi]
        c = vtxlist[ci]
        tex = texmap[texi]
        ar_x[0] = int(a.x * wscale + woff)
        ar_x[1] = int(b.x * wscale + woff)
        ar_x[2] = int(c.x * wscale + woff)
        ar_y[0] = int(a.y * hscale + hoff)
        ar_y[1] = int(b.y * hscale + hoff)
        ar_y[2] = int(c.y * hscale + hoff)
        
        sdl2.sdlgfx.texturedPolygon(renderer, ar_x, ar_y, 3, tex, 0, 0)

    shade = 0xb0
    for pl in plist:
        svtx = pl[0]
        for nvtx in pl[1:]:
            v1 = vtxlist[svtx]
            v2 = vtxlist[nvtx]
            x1 = int(v1.x * wscale + woff)
            x2 = int(v2.x * wscale + woff)
            y1 = int(v1.y * hscale + hoff)
            y2 = int(v2.y * hscale + hoff)
            sdl2.sdlgfx.lineRGBA(renderer, x1, y1, x2, y2, shade, shade, shade, 0xff)
            svtx = nvtx

    def draw_poi(poi, color, tcolor = (0xd0, 0xd0, 0xd0, 0xff)):
        step = 8
        name = poi[1]
        v = vtxlist[poi[0]]
        x = int(v.x * wscale + woff)
        y = int(v.y * hscale + hoff)
        if color:
            sz = 2
            x1 = x-sz
            x2 = x+sz
            y1 = y-sz
            y2 = y+sz
            sdl2.sdlgfx.rectangleRGBA(renderer, x1, y1, x2, y2, color[0], color[1], color[2], 0xff)
            offs = 4
            if type(name) is not str:
                return
        else: # country name: center it.
            offs = int(-len(name)*step/2)
        
        for ch in name:
            sdl2.sdlgfx.characterRGBA(renderer, x + offs, y - 4, ord(ch), tcolor[0], tcolor[1], tcolor[2], 0xff)
            offs += step

    for clabel in countrylabels:
        draw_poi(clabel, None, (0xd0, 0xd0, 0xd0, 0xff))
    
    for poi in poilist:
        if type(poi[1]) is str:
            draw_poi(poi, (0xff, 0xff, 0x00, 0xff), (0x60, 0xe0, 0x80, 0xff))
        else:
            #continue
            draw_poi(poi, (0xff, 0x00, 0xff, 0xff), 1)
            draw_poi(poi, (0xff, 0x00, 0xff, 0xff), 2)

    for q in mzquads:
        v0, v1, v2, v3 = q
        x1 = int(v0.x * wscale + woff)
        x2 = int(v1.x * wscale + woff)
        x3 = int(v2.x * wscale + woff)
        x4 = int(v3.x * wscale + woff)
        y1 = int(v0.y * hscale + hoff)
        y2 = int(v1.y * hscale + hoff)
        y3 = int(v2.y * hscale + hoff)
        y4 = int(v3.y * hscale + hoff)
        sdl2.sdlgfx.lineRGBA(renderer,x1, y1, x2, y2, 0xc0, 0x00, 0x00, 0xff)
        sdl2.sdlgfx.lineRGBA(renderer,x2, y2, x3, y3, 0xc0, 0x00, 0x00, 0xff)
        sdl2.sdlgfx.lineRGBA(renderer,x3, y3, x4, y4, 0xc0, 0x00, 0x00, 0xff)
        sdl2.sdlgfx.lineRGBA(renderer,x4, y4, x1, y1, 0xc0, 0x00, 0x00, 0xff)

    sdl2.render.SDL_RenderPresent(renderer)

def drawsurf(renderer, surf, border, blend):
    sdl2.render.SDL_SetRenderDrawColor(renderer, 0x20, 0x20, 0xf0, 255)
    sdl2.render.SDL_RenderClear(renderer)

    tex = sdl2.render.SDL_CreateTextureFromSurface(renderer, surf)
    if blend:
        sdl2.render.SDL_SetTextureBlendMode(tex, sdl2.blendmode.SDL_BLENDMODE_BLEND)
    else:
        sdl2.render.SDL_SetTextureBlendMode(tex, sdl2.blendmode.SDL_BLENDMODE_NONE)
    vp = sdl2.rect.SDL_Rect()
    sdl2.render.SDL_RenderGetViewport(renderer, ctypes.byref(vp))
    x = (vp.w - surf.contents.w)//2
    y = (vp.h - surf.contents.h)//2
    if border:
        border = sdl2.rect.SDL_Rect(x - 1, y - 1, surf.contents.w + 2, surf.contents.h + 2)
        
        sdl2.render.SDL_SetRenderDrawColor(renderer, 255, 0, 0, 255)
        sdl2.render.SDL_RenderDrawRect(renderer, border)
    dst = sdl2.rect.SDL_Rect(x, y, surf.contents.w, surf.contents.h)
    sdl2.render.SDL_RenderCopy(renderer, tex, None, ctypes.byref(dst))
    sdl2.render.SDL_RenderPresent(renderer)
    sdl2.render.SDL_DestroyTexture(tex)

def openwindow(size=(480, 320), title='xpz-wmc', icon=None, resizable = True): 
    if resizable:
        flags = sdl2.video.SDL_WINDOW_OPENGL | sdl2.video.SDL_WINDOW_RESIZABLE
    else:
        flags = sdl2.video.SDL_WINDOW_OPENGL
    window = sdl2.SDL_CreateWindow(title.encode('utf-8'),
        sdl2.video.SDL_WINDOWPOS_UNDEFINED, sdl2.video.SDL_WINDOWPOS_UNDEFINED,
        size[0], size[1], flags)
    if icon:
        sdl2.video.SDL_SetWindowIcon(window, icon)
    renderer = sdl2.render.SDL_CreateRenderer(window, -1, sdl2.render.SDL_RENDERER_ACCELERATED)
    vp = sdl2.rect.SDL_Rect(0, 0, size[0], size[1])
    sdl2.render.SDL_RenderSetViewport(renderer, ctypes.byref(vp))
    return (window, renderer)

def loop(window, renderer, choke_ms = 100):
    while True:
        loopstart = sdl2.SDL_GetTicks()
        while True:
            event = sdl2.SDL_Event()
            rv = sdl2.SDL_PollEvent(ctypes.byref(event))
            if rv == 0:
                break
            elif event.type == sdl2.SDL_QUIT:
                return            
            elif event.type == sdl2.SDL_KEYUP:
                if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                    return
            elif event.type == sdl2.SDL_WINDOWEVENT:
                if event.window.event == sdl2.SDL_WINDOWEVENT_RESIZED:
                    raise NotImplemented
                    sz = Size2(event.window.data1, event.window.data2)
                    fbo.resize(sz)
                    grid.reshape(sz)
                    hud.reshape(sz)
                    sdl2.SDL_GetWindowSize(window, ctypes.byref(w_w), ctypes.byref(w_h))
                elif sdl2.SDL_WINDOWEVENT_CLOSE:
                    continue
                    return
                else:
                    continue
                    print(event.window.event)
            elif event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                return
        elapsed = sdl2.SDL_GetTicks() - loopstart
        if choke_ms > elapsed:
            sdl2.SDL_Delay(choke_ms - elapsed)
    