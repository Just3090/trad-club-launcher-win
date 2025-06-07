#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <gl/GL.h>
#include "MinHook.h"
#include <thread>
#include <vector>
#include <string>
#include <mutex>
#pragma comment(lib, "opengl32.lib")
#pragma comment(lib, "MinHook.lib")
#pragma comment(lib, "ws2_32.lib")

typedef BOOL (WINAPI* wglSwapBuffers_t)(HDC hdc);
wglSwapBuffers_t oSwapBuffers = nullptr;

struct RectCmd {
    int x, y, w, h;
    float r, g, b, a;
};
std::vector<RectCmd> rects;
std::mutex rects_mutex;

// Simple parser for "draw_rect x y w h r g b a\n"
void parse_command(const std::string& cmd) {
    if (cmd.rfind("draw_rect", 0) == 0) {
        RectCmd rc;
        if (sscanf(cmd.c_str(), "draw_rect %d %d %d %d %f %f %f %f",
            &rc.x, &rc.y, &rc.w, &rc.h, &rc.r, &rc.g, &rc.b, &rc.a) == 8) {
            std::lock_guard<std::mutex> lock(rects_mutex);
            rects.push_back(rc);
        }
    }
    // Puedes agregar más comandos aquí (ej: clear, draw_text, etc)
}

// Socket thread: listen for commands from Python
void socket_thread() {
    WSADATA wsa;
    WSAStartup(MAKEWORD(2,2), &wsa);
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    addr.sin_port = htons(54321);
    bind(s, (sockaddr*)&addr, sizeof(addr));
    listen(s, 1);
    SOCKET client = accept(s, NULL, NULL);
    char buf[256];
    std::string partial;
    while (true) {
        int len = recv(client, buf, sizeof(buf)-1, 0);
        if (len <= 0) break;
        buf[len] = 0;
        partial += buf;
        size_t pos;
        while ((pos = partial.find('\n')) != std::string::npos) {
            std::string line = partial.substr(0, pos);
            parse_command(line);
            partial.erase(0, pos+1);
        }
    }
    closesocket(client);
    closesocket(s);
    WSACleanup();
}

BOOL WINAPI hkSwapBuffers(HDC hdc) {
    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glPushMatrix();
    GLint viewport[4];
    glGetIntegerv(GL_VIEWPORT, viewport);
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glOrtho(0, viewport[2], viewport[3], 0, -1, 1);
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();

    // Dibuja todos los rectángulos recibidos desde Python
    {
        std::lock_guard<std::mutex> lock(rects_mutex);
        for (const auto& rc : rects) {
            glEnable(GL_BLEND);
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
            glColor4f(rc.r, rc.g, rc.b, rc.a);
            glBegin(GL_QUADS);
                glVertex2i(rc.x, rc.y);
                glVertex2i(rc.x + rc.w, rc.y);
                glVertex2i(rc.x + rc.w, rc.y + rc.h);
                glVertex2i(rc.x, rc.y + rc.h);
            glEnd();
        }
    }

    glPopMatrix();
    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
    glMatrixMode(GL_MODELVIEW);
    glPopMatrix();
    glPopAttrib();

    return oSwapBuffers(hdc);
}

DWORD WINAPI InitHook(LPVOID) {
    // Inicia el thread del socket
    std::thread(socket_thread).detach();

    // Espera a que opengl32.dll esté cargado
    while (!GetModuleHandleA("opengl32.dll")) Sleep(100);

    // Obtiene la dirección de wglSwapBuffers
    HMODULE hOpenGL = GetModuleHandleA("opengl32.dll");
    void* swapAddr = reinterpret_cast<void*>(GetProcAddress(hOpenGL, "wglSwapBuffers"));

    // Inicializa MinHook
    MH_Initialize();
    MH_CreateHook(swapAddr, reinterpret_cast<LPVOID>(&hkSwapBuffers), reinterpret_cast<LPVOID*>(&oSwapBuffers));
    MH_EnableHook(swapAddr);

    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID) {
    if (ul_reason_for_call == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        CreateThread(nullptr, 0, InitHook, nullptr, 0, nullptr);
    }
    return TRUE;
}