#include <stdio.h>
#include <string.h>

int main(int count, char **arguments)
{
    const char *command = count > 1 ? arguments[1] : "";
    if (!strcmp(command, "show"))
    {
        char power[32] = "yes";
        FILE *file = fopen("radio-power", "r");
        if (file)
        {
            if (!fgets(power, sizeof(power), file))
                return 2;
            fclose(file);
            power[strcspn(power, "\r\n")] = '\0';
        }
        printf("Controller 00:11:22:33:44:55 Test\n\tPowered: %s\n", power);
    }
    else if (!strcmp(command, "info"))
        printf("Device %s\n\tName: Integration peer\n\tConnected: yes\n"
               "\tPaired: yes\n\tTrusted: yes\n", arguments[2]);
    else if (!strcmp(command, "devices") || !strcmp(command, "paired-devices"))
        puts("Device AA:BB:CC:DD:EE:FF Integration peer");
    else
        return 3;
    return 0;
}
