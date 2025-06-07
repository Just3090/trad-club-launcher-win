#include <Windows.h>
#include <d3d11.h>
#include "MinHook.h" // Incluye MinHook
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "MinHook.lib")

typedef HRESULT(__stdcall* Present_t)(IDXGISwapChain* pSwapChain, UINT SyncInterval, UINT Flags);
Present_t oPresent = nullptr;
ID3D11Device* g_pd3dDevice = nullptr;
ID3D11DeviceContext* g_pd3dDeviceContext = nullptr;
ID3D11RenderTargetView* g_mainRenderTargetView = nullptr;

// Crea un RenderTargetView si no existe
void CreateRenderTarget(IDXGISwapChain* pSwapChain) {
    if (!g_mainRenderTargetView) {
        ID3D11Texture2D* pBackBuffer = nullptr;
        pSwapChain->GetBuffer(0, __uuidof(ID3D11Texture2D), (LPVOID*)&pBackBuffer);
        if (pBackBuffer) {
            pSwapChain->GetDevice(__uuidof(ID3D11Device), (void**)&g_pd3dDevice);
            g_pd3dDevice->GetImmediateContext(&g_pd3dDeviceContext);
            g_pd3dDevice->CreateRenderTargetView(pBackBuffer, NULL, &g_mainRenderTargetView);
            pBackBuffer->Release();
        }
    }
}

// Hook de Present
HRESULT __stdcall hkPresent(IDXGISwapChain* pSwapChain, UINT SyncInterval, UINT Flags) {
    CreateRenderTarget(pSwapChain);

    if (g_pd3dDeviceContext && g_mainRenderTargetView) {
        // Dibuja un rectángulo rojo en la esquina superior izquierda
        FLOAT color[4] = { 1.0f, 0.0f, 0.0f, 0.4f }; // RGBA
        D3D11_RECT rect = { 50, 50, 300, 150 };
        g_pd3dDeviceContext->OMSetRenderTargets(1, &g_mainRenderTargetView, NULL);
        g_pd3dDeviceContext->RSSetScissorRects(1, &rect);
        g_pd3dDeviceContext->ClearRenderTargetView(g_mainRenderTargetView, color);
    }

    return oPresent(pSwapChain, SyncInterval, Flags);
}

// Inicializa el hook
DWORD WINAPI InitHook(LPVOID) {
    // Espera a que DirectX esté cargado
    while (!GetModuleHandleA("d3d11.dll")) Sleep(100);

    // Crea un dispositivo temporal para obtener la dirección de Present
    DXGI_SWAP_CHAIN_DESC sd = {};
    sd.BufferCount = 1;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow = GetForegroundWindow();
    sd.SampleDesc.Count = 1;
    sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    ID3D11Device* pDevice = nullptr;
    ID3D11DeviceContext* pContext = nullptr;
    IDXGISwapChain* pSwapChain = nullptr;

    if (FAILED(D3D11CreateDeviceAndSwapChain(
        nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0,
        D3D11_SDK_VERSION, &sd, &pSwapChain, &pDevice, nullptr, &pContext))) {
        return 1;
    }

    void** vtable = *reinterpret_cast<void***>(pSwapChain);
    void* presentAddr = vtable[8];

    // Inicializa MinHook
    MH_Initialize();
    MH_CreateHook(presentAddr, reinterpret_cast<LPVOID>(&hkPresent), reinterpret_cast<LPVOID*>(&oPresent));
    MH_EnableHook(presentAddr);

    // Limpieza
    pSwapChain->Release();
    pDevice->Release();
    pContext->Release();

    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID) {
    if (ul_reason_for_call == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        CreateThread(nullptr, 0, InitHook, nullptr, 0, nullptr);
    }
    return TRUE;
}