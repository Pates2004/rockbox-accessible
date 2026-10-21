static const char header[] =
    "sig\t1700000000.123456\t31\t:1.17\t<none>\t/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF\torg.freedesktop.DBus.Properties\tPropertiesChanged\n";

static const char classic_header[] =
    "signal time=1700000000.123456 sender=:1.17 -> destination=(null destination) serial=31 path=/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF; interface=org.freedesktop.DBus.Properties; member=PropertiesChanged\n";

static void parser_tests(void)
{
    const char *valid[] =
    {
        "sig\t0.000000\t1\t:1.2\t<none>\t/org/bluez/hci0\torg.freedesktop.DBus.Properties\tPropertiesChanged",
        "sig\t1700000000.123456\t4294967295\torg.bluez\t:1.4\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t9223372036854775807.999999\t3\torg.bluealsa\t<none>\t/org/bluealsa\torg.freedesktop.DBus.ObjectManager\tInterfacesRemoved",
        "sig\t1700000000.123456\t3\torg.freedesktop.DBus\t<none>\t/org/freedesktop/DBus\torg.freedesktop.DBus\tNameOwnerChanged",
        "sig\t1700000000.123456\t3\t:1.2\torg.example.Destination\t/org/bluez/hci123/dev_aa_BB_01_02_EE_FF\torg.freedesktop.DBus.Properties\tPropertiesChanged"
    };
    for (size_t position = 0; position < sizeof(valid) / sizeof(valid[0]); position++)
        CHECK(relevant_header(valid[position]));
    const char *invalid[] =
    {
        "#type\ttimestamp\tserial\tsender\tdestination\tpath\tinterface\tmember",
        "#\t\t\t\t\tin_reply_to",
        "PropertiesChanged",
        "   string \"PropertiesChanged\"",
        "sig\t1700000000.123456\t3\t:1.2\t<none>\t/org/bluealsa\torg.freedesktop.DBus.Properties\tPropertiesChanged",
        "sig\t1700000000.123456\t3\t:1.2\t<none>\t/org/bluez/hci0/dev_GG_BB_CC_DD_EE_FF\torg.freedesktop.DBus.Properties\tPropertiesChanged",
        "sig\t1700000000.123456\t3\t:1.2\t<none>\t/org/bluez/hci0/dev_AA\torg.freedesktop.DBus.Properties\tPropertiesChanged",
        "sig\t1700000000.123456\t3\t:1.2\t<none>\t/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/transport1\torg.freedesktop.DBus.Properties\tPropertiesChanged",
        "sig\t1700000000.123456\t3\t:1.2\t<none>\t/org/bluez/hci0oops\torg.freedesktop.DBus.Properties\tPropertiesChanged",
        "sig\t1700000000.123456\t3\t:1.2\t<none>\t/org/bluez/hci0\torg.freedesktop.DBus.Properties\tPropertiesChanged trailing",
        "sig\t1700000000.123456\t3\torg.freedesktop.DBus\t:1.4\t/org/freedesktop/DBus\torg.freedesktop.DBus\tNameAcquired",
        "sig\t1700000000.123456\t3\t:1.2\t<none>\t/org/freedesktop/DBus\torg.freedesktop.DBus\tNameOwnerChanged",
        "sig\t1.12\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.1234567\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t-1.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t9223372036854775808.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t01.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t4294967296\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t0\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t03\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "mc\t1.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "mr\t1.123456\t3\t:1.2\t<none>\t1",
        "err\t1.123456\t3\t:1.2\t<none>\t1",
        "sig\t1.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesRemovedExtra",
        "sig\t1.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded\textra",
        "sig\t1.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded\t",
        "sig\t1.123456\t3\t:1.2\t<none>\t/\torg.freedesktop.DBus.ObjectManager",
        "sig\t1.123456\t3\t:1.2\t\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\t<none>\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\t:1\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\t:1..2\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\t:1.2.\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\torg.bluez\t1.invalid\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\torg.bluealsa\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\torg.bluez\t<none>\t/org/bluealsa\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded",
        "sig\t1.123456\t3\torg.unrelated\t<none>\t/org/bluez/hci0\torg.freedesktop.DBus.Properties\tPropertiesChanged"
    };
    for (size_t position = 0; position < sizeof(invalid) / sizeof(invalid[0]); position++)
    {
        CHECK(!relevant_header(invalid[position]));
        reset_parser();
        CHECK(!parse_output(invalid[position], strlen(invalid[position])));
        CHECK(!parse_output("\n", 1));
        CHECK(parse_output(header, sizeof(header) - 1));
    }
    for (size_t split = 0; split < sizeof(header) - 1; split++)
    {
        reset_parser();
        CHECK(!parse_output(header, split));
        CHECK(parse_output(header + split, sizeof(header) - 1 - split));
    }
    reset_parser();
    for (size_t position = 0; position < sizeof(header) - 1; position++)
        CHECK(parse_output(header + position, 1) == (position == sizeof(header) - 2));
    for (unsigned int value = 0; value < 256; value++)
    {
        if (value >= 32 && value <= 126)
            continue;
        if (value == '\t' || value == '\n')
            continue;
        char malformed[sizeof(header)];
        memcpy(malformed, header, sizeof(header));
        malformed[8] = (char)value;
        reset_parser();
        CHECK(!parse_output(malformed, sizeof(malformed) - 1));
        CHECK(parse_output(header, sizeof(header) - 1));
    }
    char huge[MONITOR_LINE_SIZE + 32];
    memset(huge, 'x', sizeof(huge));
    reset_parser();
    CHECK(!parse_output(huge, sizeof(huge)));
    CHECK(!parse_output(header, sizeof(header) - 1));
    CHECK(parse_output(header, sizeof(header) - 1));
    char oversized[2048];
    int length = snprintf(oversized, sizeof(oversized),
        "sig\t1.123456\t3\t:1.%0254d\t<none>\t/\torg.freedesktop.DBus.ObjectManager\tInterfacesAdded\n", 1);
    CHECK(length > 0 && length < (int)sizeof(oversized));
    reset_parser();
    CHECK(!parse_output(oversized, (size_t)length));
    CHECK(parse_output(header, sizeof(header) - 1));
    reset_parser();
    CHECK(!parse_output(classic_header, sizeof(classic_header) - 1));
    char injected[1024];
    length = snprintf(injected, sizeof(injected), "   string \"Headset\n%s\"\n", classic_header);
    CHECK(length > 0 && length < (int)sizeof(injected));
    CHECK(!parse_output(injected, (size_t)length));
    CHECK(parse_output(header, sizeof(header) - 1));
    uint32_t random_state = UINT32_C(0x51a60fe7);
    for (size_t iteration = 0; iteration < 20000; iteration++)
    {
        char malformed[256];
        for (size_t offset = 0; offset < sizeof(malformed); offset++)
        {
            random_state ^= random_state << 13;
            random_state ^= random_state >> 17;
            random_state ^= random_state << 5;
            malformed[offset] = (char)(random_state & 255);
        }
        reset_parser();
        CHECK(!parse_output(malformed, sizeof(malformed)));
    }
}
