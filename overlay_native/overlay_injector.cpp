#include <windows.h>
#include <tlhelp32.h>
#include <iostream>

// Busca el PID de un proceso por su nombre (ejemplo: "notepad.exe")
DWORD FindProcessId(const char* processName) {
    PROCESSENTRY32 entry;
    entry.dwSize = sizeof(PROCESSENTRY32);

    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;

    if (Process32First(snapshot, &entry)) {
        do {
            if (_stricmp(entry.szExeFile, processName) == 0) {
                DWORD pid = entry.th32ProcessID;
                CloseHandle(snapshot);
                return pid;
            }
        } while (Process32Next(snapshot, &entry));
    }
    CloseHandle(snapshot);
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cout << "Uso: overlay_injector.exe <proceso.exe> <ruta\\a\\game_overlay.dll>\n";
        return 1;
    }

    const char* processName = argv[1];
    const char* dllPath = argv[2];

    DWORD pid = FindProcessId(processName);
    if (!pid) {
        std::cout << "No se encontró el proceso: " << processName << "\n";
        return 1;
    }

    HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!hProcess) {
        std::cout << "No se pudo abrir el proceso.\n";
        return 1;
    }

    // Reserva memoria en el proceso objetivo para la ruta de la DLL
    LPVOID allocMem = VirtualAllocEx(hProcess, nullptr, strlen(dllPath) + 1, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!allocMem) {
        std::cout << "No se pudo reservar memoria en el proceso.\n";
        CloseHandle(hProcess);
        return 1;
    }

    // Escribe la ruta de la DLL en el proceso objetivo
    WriteProcessMemory(hProcess, allocMem, dllPath, strlen(dllPath) + 1, nullptr);

    // Obtiene la dirección de LoadLibraryA
    LPTHREAD_START_ROUTINE loadLibraryAddr = (LPTHREAD_START_ROUTINE)GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA");

    // Crea un hilo remoto que llama a LoadLibraryA con la ruta de la DLL
    HANDLE hThread = CreateRemoteThread(hProcess, nullptr, 0, loadLibraryAddr, allocMem, 0, nullptr);
    if (!hThread) {
        std::cout << "No se pudo crear el hilo remoto.\n";
        VirtualFreeEx(hProcess, allocMem, 0, MEM_RELEASE);
        CloseHandle(hProcess);
        return 1;
    }

    // Espera a que termine el hilo
    WaitForSingleObject(hThread, INFINITE);

    // Limpieza
    VirtualFreeEx(hProcess, allocMem, 0, MEM_RELEASE);
    CloseHandle(hThread);
    CloseHandle(hProcess);

    std::cout << "¡DLL inyectada correctamente!\n";
    return 0;
}